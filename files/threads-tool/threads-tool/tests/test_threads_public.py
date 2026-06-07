import pytest

from app.services.threads_public import (
    extract_public_post_from_html,
    extract_public_profile_from_html,
    extract_shortcode,
)


PROFILE_HTML = """
<html>
  <head>
    <meta content="Mark Zuckerberg (@zuck) • Threads, Say more" property="og:title">
    <meta property="og:description" content="5.5M Followers \u2022 146 Threads \u2022 Mostly superintelligence and MMA takes. See the latest conversations with @zuck.">
    <meta property="og:image" content="https://example.com/profile.jpg">
  </head>
  <body>
    <script>{"props":{"profile":"zuck","user_id":"63055343223"}}</script>
  </body>
</html>
"""


POST_HTML = """
<html>
  <head>
    <meta property="og:title" content="Mark Zuckerberg (@zuck) on Threads">
    <meta property="og:description" content="Today Biohub is sharing a major scientific advance.">
    <meta property="og:image" content="https://example.com/post.jpg">
    <meta property="og:url" content="https://www.threads.com/@zuck/post/DY11ZLWG_eY">
  </head>
  <body>
    <script>{"props":{"post_id":"3906263078447871896","owner_id_for_crawlers":"63055343223"}}</script>
  </body>
</html>
"""


def test_extract_public_profile_from_threads_html():
    profile = extract_public_profile_from_html(PROFILE_HTML, "zuck")

    assert profile["threads_user_id"] == "63055343223"
    assert profile["username"] == "zuck"
    assert profile["full_name"] == "Mark Zuckerberg"
    assert profile["follower_count"] == 5_500_000
    assert profile["media_count"] == 146
    assert profile["biography"] == "Mostly superintelligence and MMA takes"
    assert profile["profile_pic_url"] == "https://example.com/profile.jpg"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.threads.com/t/DY11ZLWG_eY", "DY11ZLWG_eY"),
        ("https://www.threads.com/@zuck/post/DY11ZLWG_eY", "DY11ZLWG_eY"),
        ("DY11ZLWG_eY", "DY11ZLWG_eY"),
        ("3906263078447871896", None),
    ],
)
def test_extract_shortcode(value, expected):
    assert extract_shortcode(value) == expected


def test_extract_public_post_from_threads_html():
    post = extract_public_post_from_html(POST_HTML, shortcode="DY11ZLWG_eY")

    assert post["id"] == "3906263078447871896"
    assert post["code"] == "DY11ZLWG_eY"
    assert post["permalink"] == "https://www.threads.com/@zuck/post/DY11ZLWG_eY"
    assert post["text"] == "Today Biohub is sharing a major scientific advance."
    assert post["image_url"] == "https://example.com/post.jpg"
    assert post["user"]["id"] == "63055343223"
    assert post["user"]["username"] == "zuck"
