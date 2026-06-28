# Home Assistant integration

ShelfQuest Phase 1 exposes a read-only Home Assistant-friendly API endpoint for dashboarding current reading status.

The endpoint is:

```text
GET /api/integrations/home-assistant/reading
```

Example local URL:

```text
http://<shelfquest-host>:8123/api/integrations/home-assistant/reading
```

If you use the built-in HTTPS proxy for camera scanning, use the HTTPS URL instead:

```text
https://<shelfquest-host>:8443/api/integrations/home-assistant/reading
```

## What the endpoint returns

The payload includes whole-library counts and a per-child reading summary:

```json
{
  "ok": true,
  "version": "0.2.1",
  "generated_at": "2026-06-29T00:00:00+00:00",
  "total_titles": 426,
  "total_copies": 512,
  "available_copies": 489,
  "borrowed_copies": 23,
  "damaged_copies": 2,
  "total_children": 4,
  "total_active_loans": 23,
  "overdue_loans": 1,
  "children": [
    {
      "id": 1,
      "name": "Pascal",
      "slug": "pascal",
      "photo_url": "/children/child-1-example.jpg",
      "borrow_limit": 5,
      "active_loans": 2,
      "overdue_loans": 0,
      "next_due_at": "2026-07-05T00:00:00+00:00",
      "next_due_date": "2026-07-05",
      "summary": "2 books, next due 2026-07-05",
      "markdown": "- **Book title** by Author — due 2026-07-05",
      "books": []
    }
  ],
  "children_by_slug": {
    "pascal": {}
  }
}
```

## Home Assistant REST sensor

This creates one main REST sensor with all ShelfQuest data held as attributes.

```yaml
rest:
  - resource: "http://<shelfquest-host>:8123/api/integrations/home-assistant/reading"
    scan_interval: 300
    sensor:
      - name: "ShelfQuest Reading"
        unique_id: shelfquest_reading
        value_template: "{{ value_json.total_active_loans }}"
        unit_of_measurement: "books"
        json_attributes:
          - total_titles
          - total_copies
          - available_copies
          - borrowed_copies
          - damaged_copies
          - total_children
          - total_active_loans
          - overdue_loans
          - children
          - children_by_slug
          - generated_at
```

Restart Home Assistant after adding the REST sensor.

## Template sensors per child

Use the child `slug` values from the endpoint, for example `pascal`, `remy`, `amelie` or `sacha`.

```yaml
template:
  - sensor:
      - name: "ShelfQuest Pascal Reading"
        unique_id: shelfquest_pascal_reading
        state: >
          {{ state_attr('sensor.shelfquest_reading', 'children_by_slug')['pascal']['active_loans'] | default(0) }}
        unit_of_measurement: "books"
        attributes:
          summary: >
            {{ state_attr('sensor.shelfquest_reading', 'children_by_slug')['pascal']['summary'] | default('No borrowed books') }}
          markdown: >
            {{ state_attr('sensor.shelfquest_reading', 'children_by_slug')['pascal']['markdown'] | default('_No books currently borrowed._') }}
          overdue_loans: >
            {{ state_attr('sensor.shelfquest_reading', 'children_by_slug')['pascal']['overdue_loans'] | default(0) }}
          next_due_date: >
            {{ state_attr('sensor.shelfquest_reading', 'children_by_slug')['pascal']['next_due_date'] | default('') }}
```

Repeat the template sensor for each child, changing:

- the sensor name
- the `unique_id`
- the child slug

## Dashboard pattern

A Home Assistant tile card is good for the headline count. A markdown card is better for the book list.

Example vertical stack for one child:

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: sensor.shelfquest_pascal_reading
    name: Pascal
    icon: mdi:book-open-page-variant
    vertical: false
    show_entity_picture: false
    hide_state: false
  - type: markdown
    content: >
      {{ state_attr('sensor.shelfquest_pascal_reading', 'markdown') }}
```

Then create one vertical stack per child.

A practical family dashboard might use a grid card containing each child stack:

```yaml
type: grid
columns: 2
square: false
cards:
  - type: vertical-stack
    cards:
      - type: tile
        entity: sensor.shelfquest_pascal_reading
        name: Pascal
        icon: mdi:book-open-page-variant
      - type: markdown
        content: >
          {{ state_attr('sensor.shelfquest_pascal_reading', 'markdown') }}
```

## Notes

- This is read-only. Home Assistant does not write directly to `library.db`.
- No database migration is required.
- If ShelfQuest is only reachable through HTTPS with a self-signed certificate, Home Assistant may need certificate handling adjusted or you may prefer the internal HTTP Docker/LAN address for the REST sensor.
- Keep ShelfQuest and Home Assistant local to your home network unless you deliberately add proper reverse proxy, TLS and authentication controls.
