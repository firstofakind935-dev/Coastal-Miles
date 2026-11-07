from types import SimpleNamespace as NS

from coastal_miles.bot import count_images


def msg(*atts):
    return NS(attachments=[NS(content_type=c, filename=f) for c, f in atts])


def test_count_images():
    assert count_images(msg()) == 0
    assert count_images(msg(("image/png", "a.png"))) == 1
    assert count_images(msg((None, "photo.JPG"))) == 1          # no content type, use extension
    assert count_images(msg(("video/mp4", "clip.mp4"), ("application/pdf", "x.pdf"))) == 0
    assert count_images(msg(*[("image/png", f"{i}.png") for i in range(9)])) == 4  # capped
