from app.domain.entities import CollectionPage


def test_collection_pagination_rounds_up() -> None:
    page = CollectionPage(items=(), page=0, total_items=11, page_size=5)
    assert page.total_pages == 3


def test_empty_collection_has_one_display_page() -> None:
    page = CollectionPage(items=(), page=0, total_items=0, page_size=5)
    assert page.total_pages == 1

