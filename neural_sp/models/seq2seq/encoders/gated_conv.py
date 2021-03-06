#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2019 Kyoto University (Hirofumi Inaguma)
#  Apache 2.0  (http://www.apache.org/licenses/LICENSE-2.0)

"""Gated convolutional neural netwrok encoder."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import OrderedDict
import torch.nn as nn
import torch.nn.functional as F

from neural_sp.models.modules.linear import LinearND
from neural_sp.models.modules.glu import GLUBlock


class GatedConvEncoder(nn.Module):
    """Gated convolutional neural netwrok encoder.

    Args:
        input_dim (int) dimension of input features (freq * channel)
        in_channel (int) number of channels of input features
        channels (list) number of channles in TDS layers
        kernel_sizes (list) size of kernels in TDS layers
        strides (list): strides in TDS layers
        poolings (list) size of poolings in TDS layers
        dropout (float) probability to drop nodes in hidden-hidden connection
        batch_norm (bool): if True, apply batch normalization
        bottleneck_dim (int): dimension of the bottleneck layer after the last layer

    """

    def __init__(self,
                 input_dim,
                 in_channel,
                 channels,
                 kernel_sizes,
                 dropout,
                 bottleneck_dim=0):

        super(GatedConvEncoder, self).__init__()

        self.in_channel = in_channel
        assert input_dim % in_channel == 0
        self.input_freq = input_dim // in_channel
        self.bottleneck_dim = bottleneck_dim

        assert len(channels) > 0
        assert len(channels) == len(kernel_sizes)

        layers = OrderedDict()
        for l in range(len(channels)):
            layers['conv%d' % l] = GLUBlock(kernel_sizes[l][0], input_dim, channels[l],
                                            weight_norm=True,
                                            dropout=0.2)
            input_dim = channels[l]

        # weight normalization + GLU for the last fully-connected layer
        self.fc_glu = nn.utils.weight_norm(nn.Linear(input_dim, input_dim * 2),
                                           name='weight', dim=0)

        self._output_dim = int(input_dim)

        if bottleneck_dim > 0:
            self.bottleneck = LinearND(self._output_dim, bottleneck_dim)
            self._output_dim = bottleneck_dim

        self.layers = nn.Sequential(layers)

    @property
    def output_dim(self):
        return self._output_dim

    def forward(self, xs, xlens):
        """Forward computation.

        Args:
            xs (FloatTensor): `[B, T, input_dim (+Δ, ΔΔ)]`
            xlens (list): A list of length `[B]`
        Returns:
            xs (FloatTensor): `[B, T', feat_dim]`
            xlens (list): A list of length `[B]`

        """
        bs, time, input_dim = xs.size()

        # Reshape to `[B, in_ch (input_dim), T, 1]`
        xs = xs.transpose(2, 1).unsqueeze(3)

        xs = self.layers(xs)  # `[B, out_ch (feat_dim), T, 1]`

        # Collapse feature dimension
        bs, out_ch, time, freq = xs.size()
        xs = xs.transpose(2, 1).contiguous().view(bs, time, -1)

        # weight normalization + GLU for the last fully-connected layer
        xs = F.glu(self.fc_glu(xs), dim=2)

        # Reduce dimension
        if self.bottleneck_dim > 0:
            xs = self.bottleneck(xs)

        # Update xlens
        # xlens = [xlen // 8 for xlen in xlens]

        return xs, xlens
