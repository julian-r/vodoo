"""Regression tests for preserving HTML text during Markdown conversion."""

from vodoo.base import _html_to_markdown


def test_preserves_angle_bracket_placeholders_in_inline_code() -> None:
    html = "<p><code>ODP-&lt;number&gt;-&lt;slug&gt;.md</code></p>"

    assert _html_to_markdown(html) == "`ODP-<number>-<slug>.md`"


def test_preserves_angle_bracket_placeholders_in_code_block() -> None:
    html = "<pre>deploy --target &lt;environment&gt; --ref &lt;sha&gt;</pre>"

    assert _html_to_markdown(html) == "```\ndeploy --target <environment> --ref <sha>\n```"


def test_continues_decoding_ordinary_html_entities() -> None:
    html = "<p>Tom &amp; Jerry said &quot;hello&quot; &copy; 2026</p>"

    assert _html_to_markdown(html) == 'Tom & Jerry said "hello" © 2026'
