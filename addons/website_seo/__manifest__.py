{
    'name': 'Website SEO',
    'category': 'Website/Website',
    'sequence': 55,
    'summary': 'Advanced SEO tools: structured data, sitemap controls, and SEO audit dashboard',
    'version': '1.0',
    'depends': ['website'],
    'data': [
        'security/ir.model.access.csv',
        'views/website_seo_templates.xml',
        'views/website_page_views.xml',
        'data/website_seo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
