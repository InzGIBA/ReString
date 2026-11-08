import numpy as np

from _helpers import image_from_numpy, image_to_numpy
from restring.image_transformations import largest_square, resize, rgb2gray


def test_largest_square_crops_wide_image():
    img = image_from_numpy(np.arange(20 * 10 * 3).reshape((10, 20, 3)) / 600.0)

    result = largest_square(img)

    assert result.shape() == (10, 10, 3)
    np.testing.assert_allclose(image_to_numpy(result), image_to_numpy(img)[:, 5:15, :])


def test_largest_square_crops_tall_image():
    img = image_from_numpy(np.arange(200).reshape((20, 10)) / 200.0)

    result = largest_square(img)

    assert result.shape() == (10, 10, 1)
    np.testing.assert_allclose(image_to_numpy(result), image_to_numpy(img)[5:15, :])


def test_largest_square_keeps_square_image():
    img = image_from_numpy(np.ones((8, 8, 3)))

    result = largest_square(img)

    assert result.shape() == (8, 8, 3)
    np.testing.assert_allclose(image_to_numpy(result), np.ones((8, 8, 3)))


def test_resize_down_and_up():
    # a smooth gradient survives a downscale/upscale roundtrip well
    # (pure noise at Nyquist frequency cannot — that is expected aliasing loss)
    yy, xx = np.mgrid[0:32, 0:32]
    img = image_from_numpy(np.stack([xx / 32, yy / 32, (xx + yy) / 64], axis=2))

    small = resize(img, (16, 16))
    assert small.shape() == (16, 16, 3)
    back = resize(small, (32, 32))
    assert back.shape() == (32, 32, 3)
    assert np.abs(image_to_numpy(back) - image_to_numpy(img)).mean() < 0.02


def test_rgb2gray_shape_and_range():
    rng = np.random.default_rng(0)
    img = image_from_numpy(rng.random((8, 8, 3)))

    gray = rgb2gray(img)

    arr = image_to_numpy(gray)
    assert gray.shape() == (8, 8, 1)
    assert arr.min() >= 0.0
    assert arr.max() <= 1.0
    # luminance weights preserve a pure gray value (weights sum to 0.9999)
    flat = image_from_numpy(np.full((4, 4, 3), 0.5))
    np.testing.assert_allclose(image_to_numpy(rgb2gray(flat)),
                               np.full((4, 4), 0.5 * (0.2989 + 0.5870 + 0.1140)), atol=1e-12)
