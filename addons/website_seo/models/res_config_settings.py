from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    seo_json_ld_organization = fields.Boolean(
        related='website_id.seo_json_ld_organization', readonly=False,
    )
    seo_json_ld_breadcrumb = fields.Boolean(
        related='website_id.seo_json_ld_breadcrumb', readonly=False,
    )
    seo_json_ld_website = fields.Boolean(
        related='website_id.seo_json_ld_website', readonly=False,
    )
