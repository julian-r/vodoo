# Exceptions

All Vodoo exceptions inherit from `VodooError`, allowing consumers to catch a single base class.

The Odoo server-side exceptions (`OdooUserError` and subclasses) mirror the hierarchy from `odoo/exceptions.py`. When the transport layer receives an error whose `data.name` matches a known Odoo exception, it raises the corresponding Vodoo exception — so you can handle specific failure modes without parsing error strings.

```
VodooError
├── ConfigurationError
├── AuthenticationError
├── RecordNotFoundError
├── RecordOperationError
├── TransportError
│   └── OdooUserError              ← odoo.exceptions.UserError
│       ├── OdooAccessDeniedError  ← odoo.exceptions.AccessDenied
│       ├── OdooAccessError        ← odoo.exceptions.AccessError
│       ├── OdooMissingError       ← odoo.exceptions.MissingError
│       └── OdooValidationError    ← odoo.exceptions.ValidationError
└── FieldParsingError
```

## Usage

```python
from vodoo import (
    VodooError,
    AuthenticationError,
    TransportError,
    RecordNotFoundError,
)
from vodoo.exceptions import (
    OdooAccessError,
    OdooValidationError,
    OdooMissingError,
)

try:
    client.write("res.partner", [999999], {"name": "test"})
except OdooAccessError:
    print("You don't have permission for this operation")
except OdooMissingError:
    print("Record no longer exists")
except OdooValidationError as e:
    print(f"Constraint violated: {e}")
except RecordNotFoundError as e:
    print(f"Not found: {e.model} #{e.record_id}")
except TransportError as e:
    print(f"RPC error [{e.code}]: {e}")
except VodooError:
    print("Something else went wrong")
```

## Reference

::: vodoo.exceptions
    options:
      show_source: true
      members_order: source
