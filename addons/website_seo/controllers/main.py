from odoo import http
from odoo.http import request


class WebsiteSeoController(http.Controller):

    @http.route('/website_seo/dashboard_data', type='json', auth='user', website=True)
    def seo_dashboard_data(self):
        pages = request.env['website.page'].search([
            ('website_id', '=', request.website.id),
        ])
        total = len(pages)
        optimized = len(pages.filtered('is_seo_optimized'))
        not_indexed = len(pages.filtered(lambda p: not p.website_indexed))
        missing_title = len(pages.filtered(lambda p: not p.website_meta_title))
        missing_description = len(pages.filtered(lambda p: not p.website_meta_description))
        missing_keywords = len(pages.filtered(lambda p: not p.website_meta_keywords))

        avg_score = 0
        if total:
            avg_score = sum(p.seo_score for p in pages) // total

        page_list = [{
            'id': p.id,
            'name': p.name,
            'url': p.url,
            'seo_score': p.seo_score,
            'is_seo_optimized': p.is_seo_optimized,
            'website_indexed': p.website_indexed,
            'has_title': bool(p.website_meta_title),
            'has_description': bool(p.website_meta_description),
            'has_keywords': bool(p.website_meta_keywords),
        } for p in pages]

        return {
            'total_pages': total,
            'optimized_pages': optimized,
            'not_indexed_pages': not_indexed,
            'missing_title': missing_title,
            'missing_description': missing_description,
            'missing_keywords': missing_keywords,
            'avg_score': avg_score,
            'pages': page_list,
        }

    @http.route('/website_seo/json_ld', type='json', auth='public', website=True)
    def get_json_ld(self, page_url='/'):
        website = request.website
        structured_data = []

        if website.seo_json_ld_organization:
            structured_data.append(website._get_json_ld_organization())

        if website.seo_json_ld_website and page_url == '/':
            structured_data.append(website._get_json_ld_website())

        if website.seo_json_ld_breadcrumb and page_url != '/':
            breadcrumb = website._get_json_ld_breadcrumb(page_url)
            if breadcrumb:
                structured_data.append(breadcrumb)

        return structured_data
