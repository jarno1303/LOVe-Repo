def test_page_loads(page):
    assert page.locator('html').is_visible()