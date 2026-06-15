"""Supply-chain coverage & capable-to-promise (CTP) analytics.

A standalone pipeline that pulls Acumatica Generic Inquiries over OData,
loads them into a SQL star schema, disaggregates the monthly forecast into
ISO-weekly buckets, and computes:

  * a component coverage / exposure table for decoupling-point items, and
  * a capable-to-promise (CTP) ETA for each open sales-order line,

then prints a daily exception list (shortages, late POs, at-risk orders).

This is the *core-first* slice of the spec: ingest -> load -> coverage ->
ETA -> exceptions.  Acumatica write-back and the Power BI dataset are
intentionally out of scope here and stubbed for a later iteration.
"""

__version__ = "0.1.0"
