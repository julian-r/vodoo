# Exceptions

All Vodoo exceptions inherit from `VodooError`, allowing consumers to catch a single base class.

```
VodooError
├── ConfigurationError
│   └── InsecureURLError
├── AuthenticationError
├── RecordNotFoundError
├── RecordOperationError
├── TransportError
└── FieldParsingError
```

::: vodoo.exceptions
    options:
      show_source: true
      members_order: source
