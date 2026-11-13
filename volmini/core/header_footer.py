"""Header and footer data model supporting per-page customization and token expansion."""


class PageHeaderFooterConfig:
    """Header and footer text and options for a specific page or default template."""

    def __init__(
        self,
        header_left: str = "",
        header_center: str = "",
        header_right: str = "",
        footer_left: str = "",
        footer_center: str = "- {page} -",
        footer_right: str = "",
        suppressed: bool = False,
        is_custom: bool = False,
    ):
        self.header_left = header_left
        self.header_center = header_center
        self.header_right = header_right
        self.footer_left = footer_left
        self.footer_center = footer_center
        self.footer_right = footer_right
        self.suppressed = bool(suppressed)
        self.is_custom = bool(is_custom)

    def to_dict(self) -> dict:
        return {
            "header_left": self.header_left,
            "header_center": self.header_center,
            "header_right": self.header_right,
            "footer_left": self.footer_left,
            "footer_center": self.footer_center,
            "footer_right": self.footer_right,
            "suppressed": self.suppressed,
            "is_custom": self.is_custom,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PageHeaderFooterConfig":
        if not data:
            return cls()
        return cls(
            header_left=data.get("header_left", ""),
            header_center=data.get("header_center", ""),
            header_right=data.get("header_right", ""),
            footer_left=data.get("footer_left", ""),
            footer_center=data.get("footer_center", "- {page} -"),
            footer_right=data.get("footer_right", ""),
            suppressed=data.get("suppressed", False),
            is_custom=data.get("is_custom", False),
        )


class HeaderFooterModel:
    """Manages document running headers, footers, and first-page suppression."""

    def __init__(
        self,
        different_first_page: bool = True,
        first_page_config: PageHeaderFooterConfig = None,
        default_config: PageHeaderFooterConfig = None,
    ):
        self.different_first_page = bool(different_first_page)
        self.first_page_config = first_page_config or PageHeaderFooterConfig(suppressed=True, is_custom=True)
        self.default_config = default_config or PageHeaderFooterConfig()
        self.page_overrides = {}

    def get_config_for_page(self, page_num: int) -> PageHeaderFooterConfig:
        if page_num == 1 and self.different_first_page:
            return self.first_page_config
        if page_num in self.page_overrides:
            return self.page_overrides[page_num]
        return self.default_config

    @staticmethod
    def expand_tokens(
        template: str,
        page_num: int = 1,
        total_pages: int = 1,
        title: str = "",
        author: str = "",
        date: str = "2026-11-12",
    ) -> str:
        if not template:
            return ""
        res = template.replace("{page}", str(page_num))
        res = res.replace("{total}", str(max(1, total_pages)))
        res = res.replace("{title}", title or "Untitled")
        res = res.replace("{author}", author or "")
        res = res.replace("{date}", date)
        # Normalize em-dashes to clean ASCII dashes for monochrome bitmap font
        res = res.replace("\u2014", "-")
        return res

    def to_dict(self) -> dict:
        return {
            "different_first_page": self.different_first_page,
            "first_page_config": self.first_page_config.to_dict(),
            "default_config": self.default_config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HeaderFooterModel":
        if not data:
            return cls()
        return cls(
            different_first_page=data.get("different_first_page", True),
            first_page_config=PageHeaderFooterConfig.from_dict(data.get("first_page_config", {"suppressed": True})),
            default_config=PageHeaderFooterConfig.from_dict(data.get("default_config", {})),
        )
