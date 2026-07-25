from odoo import api, fields, models


class WebsitePage(models.Model):
    _inherit = 'website.page'

    sitemap_priority = fields.Float(
        "Sitemap Priority", default=0.5,
        help="Priority of this page in the sitemap (0.0 to 1.0). "
             "Higher values indicate more important pages.",
    )
    sitemap_changefreq = fields.Selection([
        ('always', 'Always'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('never', 'Never'),
    ], string="Sitemap Change Frequency", default='weekly')
    robots_directive = fields.Char(
        "Custom Robots Directive",
        help="Custom robots meta tag content (e.g. 'noindex, nofollow'). "
             "Leave empty to use defaults.",
    )
    canonical_url_override = fields.Char(
        "Canonical URL Override",
        help="Override the canonical URL for this page. "
             "Leave empty to use the auto-generated canonical URL.",
    )
    seo_score = fields.Integer(
        "SEO Score", compute='_compute_seo_score', store=True,
        help="Automated SEO quality score from 0 to 100.",
    )

    @api.depends(
        'website_meta_title', 'website_meta_description',
        'website_meta_keywords', 'website_meta_og_img',
        'website_indexed',
    )
    def _compute_seo_score(self):
        for page in self:
            score = 0
            if page.website_meta_title:
                title_len = len(page.website_meta_title)
                if 30 <= title_len <= 60:
                    score += 25
                elif title_len > 0:
                    score += 10
            if page.website_meta_description:
                desc_len = len(page.website_meta_description)
                if 120 <= desc_len <= 160:
                    score += 25
                elif desc_len > 0:
                    score += 10
            if page.website_meta_keywords:
                score += 20
            if page.website_meta_og_img:
                score += 15
            if page.website_indexed:
                score += 15
            page.seo_score = score
