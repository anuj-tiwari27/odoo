from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    seo_json_ld_organization = fields.Boolean(
        "Organization Structured Data", default=True,
        help="Include Schema.org Organization structured data on all pages.",
    )
    seo_json_ld_breadcrumb = fields.Boolean(
        "Breadcrumb Structured Data", default=True,
        help="Include Schema.org BreadcrumbList structured data on all pages.",
    )
    seo_json_ld_website = fields.Boolean(
        "WebSite Structured Data", default=True,
        help="Include Schema.org WebSite structured data on the homepage.",
    )
    default_sitemap_priority = fields.Float(
        "Default Sitemap Priority", default=0.5,
        help="Default priority for pages in the sitemap (0.0 to 1.0).",
    )

    def _get_json_ld_organization(self):
        self.ensure_one()
        company = self.company_id.sudo()
        data = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": company.name,
            "url": self.domain or '',
        }
        if company.logo_web:
            data["logo"] = self.image_url(company, 'logo_web')
        if company.phone:
            data["telephone"] = company.phone
        if company.email:
            data["email"] = company.email
        social = []
        for field_name in ('social_facebook', 'social_twitter', 'social_linkedin',
                           'social_youtube', 'social_instagram', 'social_github'):
            url = getattr(company, field_name, None)
            if url:
                social.append(url)
        if social:
            data["sameAs"] = social
        return data

    def _get_json_ld_website(self):
        self.ensure_one()
        return {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": self.name,
            "url": self.domain or '',
        }

    def _get_json_ld_breadcrumb(self, path):
        self.ensure_one()
        parts = [p for p in path.strip('/').split('/') if p]
        if not parts:
            return None
        base_url = self.domain or ''
        items = [{
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": base_url + '/',
        }]
        accumulated = ''
        for i, part in enumerate(parts):
            accumulated += '/' + part
            items.append({
                "@type": "ListItem",
                "position": i + 2,
                "name": part.replace('-', ' ').title(),
                "item": base_url + accumulated,
            })
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items,
        }
