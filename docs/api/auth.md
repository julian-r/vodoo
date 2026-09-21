# Auth

Authentication utilities and requested-author message operations. Cross-user attribution requires an internal authenticated user. Odoo may reject or override it for share users, which can reliably attribute only to their own partner. Selecting an author does not change authenticated identity, access checks, or auditing.

::: vodoo.auth
    options:
      show_source: true
      members_order: source
