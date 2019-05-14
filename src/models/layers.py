from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

from models.variables import tf_variable


def get_act_fn(act_fn):
  """
  Helper to get activation function from name.
  """
  if act_fn == 'relu':
    activation_fn = tf.nn.relu
  elif act_fn == 'sigmoid':
    activation_fn = tf.nn.sigmoid
  elif act_fn == 'elu':
    activation_fn = tf.nn.elu
  elif act_fn is None:
    activation_fn = None
  else:
    raise ValueError('Wrong activation function name!')
  return activation_fn


class Sequential(object):
  """Build models architecture by sequential."""
  def __init__(self, inputs, verbose=False):
    self._top = inputs
    self._info = []
    self.verbose = verbose
    self.i = 1
    if verbose:
      print('[1]  Inputs: ', inputs.get_shape().as_list())

  def add(self, layer, **vars):
    """Add a layer to the top of the models.

    Args:
      layer: the layer to be added
      assign_variables: assign existed variables, (weights, biases)
    """
    if vars:
      layer.assign_variables(**vars)
    self._top = layer(self._top)
    layer_name_ = layer.__class__.__name__
    layer_params_ = layer.params
    layer_output_shape_ = layer.output_shape
    self._info.append((layer_name_, layer_params_, layer_output_shape_))
    if self.verbose:
      self.i += 1
      print('[%d] ' % self.i, layer_name_, ': ', layer_output_shape_)

  @property
  def top_layer(self):
    """The top layer of the models."""
    return self._top

  @property
  def info(self):
    """The architecture information of the models."""
    return self._info

  def get_loss(self, loss_fn, labels, **loss_fn_params):
    loss, preds = loss_fn(self._top, labels, **loss_fn_params)
    return loss, preds
  
  def add_name(self, name):
    self._top = tf.identity(self._top, name=name)


class ModelBase(object):

  def __init__(self):
    self.output = None
    self.assign_vars = False
    self.weights = None
    self.biases = None
    self.trainable = True

  @property
  def params(self):
    """Get parameters of this layer."""
    pop_key_list = [
      'cfg', 'output', 'is_training', 'labels',
      'act_function', 'weights', 'biases'
    ]
    return {item[0]: item[1] for item in self.__dict__.items()
            if item[0] not in pop_key_list}

  @property
  def output_shape(self):
    return self.output.get_shape().as_list()

  def assign_variables(self, weights, biases, trainable=True):
    self.assign_vars = True
    self.weights = weights
    self.biases = biases
    self.trainable = trainable

  def _get_variables(self,
                     use_bias=True,
                     weights_shape=None,
                     biases_shape=None,
                     weights_initializer=tf.contrib.layers.xavier_initializer(),
                     biases_initializer=tf.zeros_initializer(),
                     store_on_cpu=True):
    if self.assign_vars:
      assert weights_shape == list(self.weights.shape), \
        'Shapes of weights are not matched: {} & {}'.format(
            weights_shape, self.weights.shape)
      weights_initializer = tf.constant_initializer(self.weights)
    weights = tf_variable(name='weights',
                          shape=weights_shape,
                          initializer=weights_initializer,
                          store_on_cpu=store_on_cpu,
                          trainable=self.trainable)

    if use_bias:
      if self.assign_vars:
        assert biases_shape == list(self.biases.shape), \
          'Shapes of biases are not matched: {} & {}'.format(
              biases_shape, self.biases.shape)
        biases_initializer = tf.constant_initializer(self.biases)
      biases = tf_variable(name='biases',
                           shape=biases_shape,
                           initializer=biases_initializer,
                           store_on_cpu=store_on_cpu,
                           trainable=self.trainable)
    else:
      biases = None

    return weights, biases


class Dense(ModelBase):

  def __init__(self,
               cfg,
               output_dim=None,
               act_fn='relu',
               use_bias=True,
               idx=0):
    """Single full-connected layer

    Args:
      cfg: configuration
      output_dim: hidden units of full_connected layer
      act_fn: activation function
      use_bias: if use bias
      idx: index of layer
    """
    super(Dense, self).__init__()
    self.cfg = cfg
    self.output_dim = output_dim
    self.act_fn = act_fn
    self.use_bias = use_bias
    self.idx = idx

  def __call__(self, inputs):
    """Single full-connected layer

    Args:
      inputs: input tensor
        - shape: (batch_size, num_units)

    Returns:
      output tensor of full-connected layer
    """
    with tf.variable_scope('fc_{}'.format(self.idx)):
      activation_fn = get_act_fn(self.act_fn)

      weights_initializer = tf.contrib.layers.xavier_initializer()
      biases_initializer = tf.zeros_initializer() if self.use_bias else None
      # weights_initializer = tf.truncated_normal_initializer(
      #     stddev=0.1, dtype=tf.float32)
      # biases_initializer = tf.constant_initializer(0.1) \
      #     if self.use_bias else None

      weights, biases = self._get_variables(
          use_bias=self.use_bias,
          weights_shape=[inputs.get_shape().as_list()[1], self.output_dim],
          biases_shape=[self.output_dim],
          weights_initializer=weights_initializer,
          biases_initializer=biases_initializer,
          store_on_cpu=self.cfg.VAR_ON_CPU
      )

      self.output = tf.matmul(inputs, weights)

      if self.use_bias:
        self.output = tf.add(self.output, biases)

      if activation_fn is not None:
        self.output = activation_fn(self.output)

      return self.output


class Conv(ModelBase):

  def __init__(self,
               cfg,
               kernel_size=None,
               stride=None,
               n_kernel=None,
               padding='VALID',
               act_fn='relu',
               resize=None,
               use_bias=True,
               atrous=False,
               idx=0):
    """Single convolution layer

    Args:
      cfg: configuration
      kernel_size: size of convolution kernel
      stride: stride of convolution kernel
      n_kernel: number of convolution kernels
      padding: padding type of convolution kernel
      act_fn: activation function
      resize: if resize is not None, resize every image
      atrous: use atrous convolution
      use_bias: use bias
      idx: index of layer
    """
    super(Conv, self).__init__()
    self.cfg = cfg
    self.kernel_size = kernel_size
    self.stride = stride
    self.n_kernel = n_kernel
    self.padding = padding
    self.act_fn = act_fn
    self.resize = resize
    self.use_bias = use_bias
    self.atrous = atrous
    self.idx = idx

  def __call__(self, inputs):
    """Single convolution layer

    Args:
      inputs: 4D tensor of shape
      `[batch, input_channels, input_height, input_width]`.

    Returns:
      output: 4D tensor of shape
      `[batch, output_channels, output_height, output_width]`.

    """
    with tf.variable_scope('conv_{}'.format(self.idx)):
      # Resize image
      if self.resize is not None:
        inputs_trans = tf.transpose(inputs, [0, 2, 3, 1])
        inputs_resized = tf.image.resize_nearest_neighbor(
            inputs_trans, (self.resize, self.resize))
        inputs = tf.transpose(inputs_resized, [0, 3, 1, 2])

      # With atrous
      if not self.atrous and self.stride > 1:
        pad = self.kernel_size - 1
        pad_beg = pad // 2
        pad_end = pad - pad_beg
        inputs = tf.pad(
            inputs, [[0, 0], [0, 0], [pad_beg, pad_end], [pad_beg, pad_end]])
        self.padding = 'VALID'

      activation_fn = get_act_fn(self.act_fn)

      weights_initializer = tf.contrib.layers.xavier_initializer()
      biases_initializer = tf.zeros_initializer() if self.use_bias else None
      # weights_initializer = tf.truncated_normal_initializer(
      #     stddev=0.1, dtype=tf.float32)
      # biases_initializer = tf.constant_initializer(0.1) \
      #     if self.use_bias else None

      weights, biases = self._get_variables(
          use_bias=self.use_bias,
          weights_shape=[self.kernel_size, self.kernel_size,
                         inputs.get_shape().as_list()[1], self.n_kernel],
          biases_shape=[self.n_kernel],
          weights_initializer=weights_initializer,
          biases_initializer=biases_initializer,
          store_on_cpu=self.cfg.VAR_ON_CPU
      )

      self.output = tf.nn.conv2d(input=inputs,
                                 filter=weights,
                                 strides=[1, self.stride, self.stride, 1],
                                 padding=self.padding,
                                 data_format='NCHW')

      if self.use_bias:
        self.output = tf.nn.bias_add(self.output, biases, data_format='NCHW')

      if activation_fn is not None:
        self.output = activation_fn(self.output)

      return self.output


class ConvT(ModelBase):

  def __init__(self,
               cfg,
               kernel_size=None,
               stride=None,
               n_kernel=None,
               padding='VALID',
               act_fn='relu',
               output_shape=None,
               use_bias=True,
               idx=None):
    """Single transpose convolution layer

    Args:
      cfg: configuration
      kernel_size: size of convolution kernel
      stride: stride of convolution kernel
      n_kernel: number of convolution kernels
      padding: padding type of convolution kernel
      act_fn: activation function
      output_shape: output shape of deconvolution layer
      use_bias: use bias
      idx: index of layer
    """
    super(ConvT, self).__init__()
    self.cfg = cfg
    self.kernel_size = kernel_size
    self.stride = stride
    self.n_kernel = n_kernel
    self.padding = padding
    self.act_fn = act_fn
    self.conv_t_output_shape = output_shape
    self.use_bias = use_bias
    self.idx = idx

  def __call__(self, inputs):
    """Single transpose convolution layer

    Args:
      inputs: 4D tensor of shape
      `[batch, input_channels, input_height, input_width]`.

    Returns:
      output: 4D tensor of shape
      `[batch, output_channels, output_height, output_width]`.
    """
    with tf.variable_scope('conv_t_{}'.format(self.idx)):
      activation_fn = get_act_fn(self.act_fn)

      weights_initializer = tf.contrib.layers.xavier_initializer()
      biases_initializer = tf.zeros_initializer() if self.use_bias else None
      # weights_initializer = tf.truncated_normal_initializer(
      #     stddev=0.1, dtype=tf.float32)
      # biases_initializer = tf.constant_initializer(0.1) \
      #     if self.use_bias else None

      weights, biases = self._get_variables(
          use_bias=self.use_bias,
          weights_shape=[self.kernel_size, self.kernel_size,
                         self.n_kernel, inputs.get_shape().as_list()[1]],
          biases_shape=[self.n_kernel],
          weights_initializer=weights_initializer,
          biases_initializer=biases_initializer,
          store_on_cpu=self.cfg.VAR_ON_CPU
      )

      self.output = tf.nn.conv2d_transpose(
          value=inputs,
          filter=weights,
          output_shape=self.conv_t_output_shape,
          strides=[1, self.stride, self.stride, 1],
          padding=self.padding,
          data_format='NCHW'
      )

      if self.use_bias:
        self.output = tf.nn.bias_add(self.output, biases, data_format='NCHW')

      if activation_fn is not None:
        self.output = activation_fn(self.output)

      return self.output


class MaxPool(ModelBase):

  def __init__(self,
               cfg,
               pool_size=None,
               strides=None,
               padding='valid',
               idx=None):
    """Max Pooling layer.

    Args:
      cfg: configuration
      pool_size: specifying the size of the pooling window
      strides: specifying the strides of the pooling operation
      padding: the padding method, either 'valid' or 'same'
      idx: index of layer
    """
    super(MaxPool, self).__init__()
    self.cfg = cfg
    self.pool_size = pool_size
    self.strides = strides
    self.padding = padding
    self.idx = idx

  def __call__(self, inputs):
    """Max Pooling layer.

    Args:
      inputs: input tensor

    Returns:
      max pooling tensor
    """
    with tf.variable_scope('max_pool_{}'.format(self.idx)):
      self.output = tf.layers.max_pooling2d(
          inputs=inputs,
          pool_size=self.pool_size,
          strides=self.strides,
          padding=self.padding,
          data_format='NCHW'
      )

    return self.output


class AveragePool(ModelBase):

  def __init__(self,
               cfg,
               pool_size=None,
               strides=None,
               padding='valid',
               idx=None):
    """Average Pooling layer.

    Args:
      cfg: configuration
      pool_size: specifying the size of the pooling window
      strides: specifying the strides of the pooling operation
      padding: the padding method, either 'valid' or 'same'
      idx: index of layer
    """
    super(AveragePool, self).__init__()
    self.cfg = cfg
    self.pool_size = pool_size
    self.strides = strides
    self.padding = padding
    self.idx = idx

  def __call__(self, inputs):
    """Average Pooling layer.

    Args:
      inputs: input tensor

    Returns:
      average pooling tensor
    """
    with tf.variable_scope('avg_pool_{}'.format(self.idx)):
      self.output = tf.layers.average_pooling2d(
          inputs=inputs,
          pool_size=self.pool_size,
          strides=self.strides,
          padding=self.padding,
          data_format='NCHW'
      )

    return self.output


class GlobalAveragePool(ModelBase):

  def __init__(self):
    """Global Average Pooling layer."""
    super(GlobalAveragePool, self).__init__()

  def __call__(self, inputs):
    """Average Pooling layer.

    Args:
      inputs: input tensor, must have 4 dims

    Returns:
      global average pooling tensor
    """
    with tf.variable_scope('gap'):
      assert inputs.get_shape().ndims == 4
      self.output = tf.reduce_mean(inputs, [2, 3])
    return self.output


class BatchNorm(ModelBase):

  def __init__(self,
               cfg,
               is_training,
               momentum=0.99,
               center=True,
               scale=True,
               epsilon=0.001,
               act_fn='relu',
               idx=None):
    """Batch normalization layer.

    Args:
      cfg: configuration
      is_training: Whether or not the layer is in training mode.
      momentum: Momentum for the moving average.
      center: If True, add offset of beta to normalized tensor.
              If False, beta is ignored.
      scale: If True, multiply by gamma. If False, gamma is not used.
      epsilon: Small float added to variance to avoid dividing by zero.
      act_fn: Add a activation function after batch normalization layer.
              If None, not add.
      idx: index of layer
    """
    super(BatchNorm, self).__init__()
    self.cfg = cfg
    self.is_training = is_training
    self.momentum = momentum
    self.center = center
    self.scale = scale
    self.epsilon = epsilon
    self.act_fn = act_fn
    self.idx = idx

  def __call__(self, inputs):
    """
    Batch normalization layer.

    Args:
      inputs: input tensor

    Returns:
      batch normalization tensor
    """
    with tf.variable_scope('bn_{}'.format(self.idx)):
      self.output = tf.layers.batch_normalization(
          inputs=inputs,
          momentum=self.momentum,
          center=self.center,
          scale=self.scale,
          epsilon=self.epsilon,
          training=self.is_training)

      if self.act_fn is not None:
        activation_fn = get_act_fn(self.act_fn)
        self.output = activation_fn(self.output)

    return self.output


class Reshape(ModelBase):

  def __init__(self, shape, name=None):
    """Reshape a tensor.

    Args:
      shape: shape of output tensor
      name: name of output tensor
    """
    super(Reshape, self).__init__()
    self.shape = shape
    self.name = name

  def __call__(self, inputs):
    """Reshape a tensor.

    Args:
      inputs: input tensor

    Returns:
      reshaped tensor
    """
    self.output = tf.reshape(inputs, shape=self.shape, name=self.name)
    return self.output


class NHWC2NCHW(ModelBase):

  def __init__(self):
    super(NHWC2NCHW, self).__init__()

  def __call__(self, inputs):
    """Convert a NHWC tensor to NCHW tensor.

    Args:
      inputs: 4D tensor of shape `[batch, height, width, channels]`.

    Returns:
      output: 4D tensor of shape `[batch, channels, height, width]`.
    """
    self.output = tf.transpose(inputs, [0, 3, 1, 2])
    return self.output


class NCHW2NHWC(ModelBase):

  def __init__(self):
    super(NCHW2NHWC, self).__init__()

  def __call__(self, inputs):
    """Convert a NCHW tensor to NHWC tensor.

    Args:
      inputs: 4D tensor of shape `[batch, channels, height, width]`.

    Returns:
      output: 4D tensor of shape `[batch, height, width, channels]`.
    """
    self.output = tf.transpose(inputs, [0, 2, 3, 1])
    return self.output
