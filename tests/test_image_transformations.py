import numpy as np

from restring.image_transformations import largest_square, rgb2gray


def test_largest_square_crops_wide_image():
    img = np.arange(20 * 10 * 3).reshape((10, 20, 3))

    result = largest_square(img)

    assert result.shape == (10, 10, 3)
    # crops columns around the centre: keeps columns 5..14
    np.testing.assert_array_equal(result, img[:, 5:15, :])


def test_largest_square_crops_tall_image():
    img = np.arange(20 * 10).reshape((20, 10))

    result = largest_square(img)

    assert result.shape == (10, 10)
    # crops rows around the centre: keeps rows 5..14
    np.testing.assert_array_equal(result, img[5:15, :])


def test_largest_square_keeps_square_image():
    img = np.ones((8, 8, 3))

    result = largest_square(img)

    assert result.shape == (8, 8, 3)
    np.testing.assert_array_equal(result, img)


def test_rgb2gray_shape_and_range():
    rng = np.random.default_rng(0)
    img = rng.random((8, 8, 3))

    gray = rgb2gray(img)

    assert gray.shape == (8, 8)
    assert gray.min() >= 0.0
    assert gray.max() <= 1.0
