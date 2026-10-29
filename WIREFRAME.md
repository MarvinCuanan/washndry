# Wash 'n Dry Pre-Implementation Wireframe

This text wireframe documents the intended screen flow and can be recreated in
Figma, Canva, or on paper for the required dated pre-coding artifact.

```text
+---------------------------------------------------------------+
| Wash 'n Dry                         [user] [role]              |
+-------------+-------------------------------------------------+
| Dashboard   | Page title                                      |
| Customers   | [Search] [Add] [Edit] [Delete]                  |
| Services    |                                                 |
| Orders      | +---------------------------------------------+ |
| Payments    | | ID | Customer | Total | Status | Date       | |
| Order Status| +---------------------------------------------+ |
| Reports     |                                                 |
| Users       | [Back] [Cancel] [Save]                         |
| Logout      |                                                 |
+-------------+-------------------------------------------------+
```

Flow: Login -> Dashboard -> one of the management pages -> form -> validation
message or confirmation -> list page. Viewer users skip write controls; Admin
users additionally access Services and Users.

The sidebar was selected so users always know their location and can return to
another page without restarting. Status colors distinguish operational states,
and confirmation dialogs reduce accidental destructive actions.
