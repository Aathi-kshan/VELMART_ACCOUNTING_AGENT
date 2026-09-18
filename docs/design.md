# Velmart UI/UX Design System

> **Status:** Design handoff for the existing Flutter application  
> **Scope:** V1 UI/UX system and screen-level guidance  
> **Primary sources:** current implementation inventory and verification notes in `IMPLEMENTATION_PLAN(4).md`, locked product/technical specification in `PROJECT_PLAN(2).md`, and the supplied Velmart logo assets.  
> **Implementation instruction:** This document defines the visual system and UI behavior. It does **not** authorize product-scope changes. Existing architecture, routes, permissions, and data contracts remain the source of truth.

---

## 0. Design-system operating rules

Velmart is a business application for supermarket owners and managers who need to record, review, reconcile, and understand daily business data quickly.

The UI must optimize for:

1. **Speed of comprehension**
2. **Low input friction**
3. **High financial clarity**
4. **Visible system state**
5. **Predictable navigation**
6. **Role-appropriate controls**
7. **Adaptive layouts**
8. **Auditability and trust**

The visual language should be quiet and functional. Brand color creates hierarchy; it must not become decoration.

### Current implementation baseline

The implementation plan records the following Flutter surfaces as written and compiler-verified:

- authentication/login and home shell
- adaptive scaffold
- page list
- record list
- record detail
- record form
- filters
- page builder
- column editor
- access editor
- field renderers
- reconciliation
- CSV export/import history work that was present historically
- audit list
- dashboard rendering
- dashboard widget configuration code

The same implementation record states that P1–P5 Flutter code has been compiler-verified with `dart analyze --fatal-infos` and `flutter test`; a Flutter web debug build also succeeded. `IMPLEMENTATION_PLAN(4).md` separately marks offline support as deferred, AI read/write as not started, and attachments as deferred.

**Scope reconciliation rule:** product decisions in the latest locked `PROJECT_PLAN(2).md` override historical implementation rows. In particular:

- CSV **export** remains.
- CSV **import** was removed from the current product scope.
- `page_validations` / the Validation Rules editor was removed from the current product scope.
- Dashboard widget **creation** / “Add widget” / starter suggestions were removed from the current product scope. Existing widgets can still be viewed, edited, or deleted according to the current plan.
- Attachments are deferred and should not be presented as a completed V1 workflow.
- Offline sync is deferred; current release assumes reliable internet.
- AI read/write are future implementation stages, but this design system defines their intended future UI so implementation remains visually consistent.

Do not redesign the application around removed modules simply because legacy code or historical plan rows mention them.

---

# 1. Design vision

## 1.1 Product character

Velmart should feel like:

> **A clean supermarket operations control panel built around simple records, reliable numbers, and fast decisions.**

It should combine:

- the familiarity of a spreadsheet,
- the discipline of a structured business system,
- the clarity of a modern mobile app,
- and the confidence of an accounting tool.

It must **not** feel like:

- a generic admin template,
- a complicated ERP,
- a developer database console,
- a social/chat application,
- a chart-heavy BI platform,
- or a consumer finance app.

## 1.2 UX principles

### Principle A — One primary action

Every screen has one visually dominant action.

Examples:

- Page list → open a page
- Record list → add a record
- Record detail → review or owner-edit
- Page builder → save the page structure
- Dashboard → understand the business
- Audit → inspect what changed
- AI → ask a question / review an update

Secondary actions are quieter.

### Principle B — Money is visually precise

Monetary values must be:

- right-aligned in dense tables,
- formatted consistently as LKR,
- never visually ambiguous,
- never displayed with unnecessary decimals for ordinary whole-rupee values,
- and never rendered as approximate values when the source is exact.

Suggested display:

`Rs. 250,000`

Not:

`250000`

Not:

`~250K`

Not:

`250k`

Use the existing `Money` value object and `AmountText` component for presentation.

### Principle C — Record first, configuration second

Managers primarily record business data. Owners can configure structure.

Therefore:

- data-entry UI should be simpler than configuration UI,
- advanced controls should live behind clear menus,
- Owner-only controls must not clutter Manager screens.

### Principle D — State is always visible

The user should quickly know:

- whether the page is loaded,
- whether data is filtered,
- whether a save succeeded,
- whether an action failed,
- whether data is current,
- and who can perform a restricted action.

### Principle E — Never hide important exceptions

A reconciliation difference, validation error, permission denial, stale AI proposal, or server failure is not a decorative alert.

It is business information and must be prominent without becoming visually alarming.

---

# 2. Brand identity

## 2.1 Logo analysis

Two supplied Velmart logo treatments were reviewed:

### Primary logo treatment

The first asset is a bright green Velmart mark on white:

- large stylized `V` silhouette,
- integrated leaf/feather-like shape,
- central peacock motif,
- white internal negative space,
- optimistic, natural, fresh appearance,
- strong symmetrical geometry.

The dominant sampled brand family is approximately:

- RGB around `68, 192, 69`
- HEX approximately **`#44C045`**

A darker green region is also present around:

- RGB approximately `19, 164, 69`
- HEX approximately **`#13A445`**

These values are practical UI approximations from the supplied raster image, not an official corporate color specification.

### Secondary logo treatment

The second supplied asset uses a blue-to-green transition:

- blue/teal upper areas,
- green lower areas,
- same Velmart mark,
- transparent/dark presentation.

A representative blue region is approximately:

- RGB around `30, 128, 165`
- HEX approximately **`#1E80A5`**

Representative transitional greens are around:

- **`#56A76D`**
- **`#5CAD68`**

### Design conclusion

Use **green as the primary brand anchor** and **blue/teal as a restrained secondary family**.

The full UI should not reproduce the logo gradient everywhere. The gradient belongs to brand artwork and selected hero/brand moments. Core business UI should use solid colors for accessibility, scanability, and consistent interaction semantics.

---

# 3. Logo usage

## 3.1 Logo variants

Define three UI usage modes:

| Variant | Use |
|---|---|
| Full logo | Login, welcome, onboarding/brand moments |
| Mark only | App shell, small navigation surfaces, app icon |
| Mark + wordmark | Wide desktop sidebar/header where space permits |

## 3.2 Clear space

Keep clear space around the logo equal to at least the width of the inner peacock head/neck unit.

Do not:

- place controls directly against the logo,
- crop the mark,
- stretch it,
- skew it,
- rotate it,
- add shadows,
- place text over the symbol,
- replace its colors with random theme colors.

## 3.3 Backgrounds

Preferred:

- white,
- `Brand Green 700` or another approved deep green,
- very light neutral background.

Avoid placing the primary logo on noisy imagery.

## 3.4 Minimum size

For raster or vector rendering:

- mobile mark: ~24–28 dp minimum,
- sidebar mark: 30–36 dp,
- login mark: 72–120 dp depending on available space.

Maintain optical rather than mathematical centering.

---

# 4. Complete color system

## 4.1 Color tokens

### Brand

| Token | HEX | Usage |
|---|---|---|
| `brandPrimary` | `#44C045` | Brand recognition, selected accents, highlights |
| `brandPrimaryDark` | `#168B45` | Filled actions, dark green surfaces |
| `brandPrimaryDeep` | `#0F6F3B` | Strong text/icon contrast where green is required |
| `brandPrimarySoft` | `#EAF8EC` | Selected backgrounds, subtle success tint |
| `brandPrimaryMuted` | `#CBE9CF` | Borders, non-critical emphasis |

### Secondary blue/teal

| Token | HEX | Usage |
|---|---|---|
| `brandSecondary` | `#1E80A5` | Secondary actions, analytical accents |
| `brandSecondaryDark` | `#155F7D` | Strong secondary button/text |
| `brandSecondarySoft` | `#EAF5F8` | Secondary panels and informative surfaces |
| `brandTeal` | `#4FA88B` | Optional bridge color in brand visuals only |

### App surfaces

| Token | HEX | Usage |
|---|---|---|
| `background` | `#F6F9F7` | Main application background |
| `surface` | `#FFFFFF` | Cards, sheets, tables, forms |
| `surfaceSubtle` | `#F1F5F2` | Secondary rows, grouped field areas |
| `surfaceElevated` | `#FFFFFF` | Dialogs/popovers |
| `surfaceDisabled` | `#ECEFEC` | Disabled controls |

### Text

| Token | HEX | Usage |
|---|---|---|
| `textPrimary` | `#17221B` | Headings, primary values |
| `textSecondary` | `#536159` | Supporting text |
| `textTertiary` | `#738078` | Metadata, hints |
| `textOnBrand` | `#FFFFFF` | Text on deep brand surfaces |
| `textDisabled` | `#99A39C` | Disabled labels |
| `textLink` | `#155F7D` | Secondary links |

### Borders

| Token | HEX | Usage |
|---|---|---|
| `border` | `#D8E2DB` | Inputs, cards, dividers |
| `borderStrong` | `#C1CEC5` | Active table separators |
| `borderFocus` | `#168B45` | Keyboard/focus state |
| `borderDisabled` | `#E5EAE6` | Disabled inputs |

### Semantic colors

| Token | HEX | Usage |
|---|---|---|
| `success` | `#2F9959` | Successful save, matched reconciliation |
| `successSoft` | `#EAF7EF` | Success containers |
| `warning` | `#C98A16` | Attention, pending, non-blocking warning |
| `warningSoft` | `#FFF6DF` | Warning banners |
| `error` | `#C94B4B` | Blocking errors, failed operations |
| `errorSoft` | `#FCECEC` | Error containers |
| `info` | `#2B7EA0` | Informational notices |
| `infoSoft` | `#EAF5F8` | Informational containers |

### Reconciliation semantic treatment

Do not invent a special accounting rainbow.

- balanced / exact zero difference → `success`
- non-zero difference requiring attention → `warning` or `error` according to business severity
- informational “no ledger row yet” → `info` plus a clear textual explanation

## 4.2 Color usage ratio

Target approximate visual ratio:

- 70% neutral surfaces,
- 20% typography and borders,
- 7% brand/secondary accents,
- 3% semantic state colors.

Do not color entire tables green.

## 4.3 Accessibility rule

Never rely on color alone.

Examples:

- a warning difference also includes an icon and text,
- a protected field has a lock indicator and helper text,
- a sync state has an icon and label,
- error messages include explicit wording.

---

# 5. Typography system

## 5.1 Font

Preferred product font: **Inter**.

Fallback:

1. system sans-serif,
2. platform default sans-serif.

Do not use decorative fonts.

## 5.2 Scale

| Token | Size | Weight | Use |
|---|---:|---:|---|
| `display` | 30 | 700 | Major page/brand heading |
| `h1` | 26 | 700 | Screen title |
| `h2` | 22 | 700 | Major section |
| `h3` | 18 | 700 | Card/section title |
| `title` | 16 | 650 | App-bar/subsection title |
| `body` | 14 | 400 | Default content |
| `bodyMedium` | 14 | 550 | Important body text |
| `bodySmall` | 12 | 400 | Metadata |
| `label` | 12 | 600 | Field labels/buttons |
| `caption` | 11 | 500 | Secondary metadata |
| `data` | 14 | 500 | Table values |
| `dataStrong` | 14 | 650 | Key financial values |

## 5.3 Line height

- headings: 1.2–1.25
- body: 1.4–1.5
- table data: 1.25–1.35
- helper text: 1.35–1.45

## 5.4 Financial typography

Amounts should use consistent numeric alignment.

Desktop table:

- numeric columns right-aligned,
- currency symbol and value visually grouped,
- no excessive bolding.

Dashboard metric:

- value 28–36 dp,
- label 12–14 dp,
- comparison beneath the number.

---

# 6. Spacing system

Use a 4 dp base scale.

| Token | dp | Use |
|---|---:|---|
| `space1` | 4 | icon/text micro-gap |
| `space2` | 8 | compact field gap |
| `space3` | 12 | row inner spacing |
| `space4` | 16 | standard content gap |
| `space5` | 20 | section gap |
| `space6` | 24 | card padding / major gap |
| `space7` | 32 | page section separation |
| `space8` | 40 | large hero separation |
| `space9` | 48 | major desktop spacing |
| `space10` | 64 | brand/empty state composition |

### Default paddings

- mobile screen horizontal padding: 16 dp
- tablet: 20–24 dp
- desktop content: 24–32 dp
- card: 16–20 dp
- dialog: 24 dp
- table cell horizontal: 12 dp minimum
- form field vertical gap: 12–16 dp

---

# 7. Border radius and elevation

## 7.1 Radius scale

| Token | dp | Use |
|---|---:|---|
| `radiusXs` | 4 | compact badges/chips |
| `radiusSm` | 8 | buttons, text fields |
| `radiusMd` | 12 | cards |
| `radiusLg` | 16 | larger surfaces/sheets |
| `radiusXl` | 24 | hero/welcome surfaces |
| `radiusPill` | 999 | status chips |

Use 12 dp as the default application card radius.

## 7.2 Elevation

Keep elevation subtle.

- base surfaces: 0
- cards: 1
- floating controls: 2–4
- modal dialogs: 6–12

Prefer border + surface separation over heavy shadows.

Do not use glassmorphism.

---

# 8. Iconography

## 8.1 Icon family

Use Flutter Material icons or another single, consistent icon family already adopted by the project.

Avoid mixing:

- outlined and filled variants unpredictably,
- emoji as UI icons,
- unrelated icon packs.

## 8.2 Size

| Context | Size |
|---|---:|
| Inline | 16 |
| Compact button | 18 |
| Standard action | 20 |
| Navigation | 22–24 |
| Empty state | 32–48 |
| Hero brand | logo, not generic icon |

## 8.3 Semantic icon convention

- add → `add`
- search → `search`
- filter → `filter_alt`
- sort → `sort`
- settings → `settings_outlined`
- owner/settings/security → appropriate neutral settings icons
- protected → `lock_outline`
- success → `check_circle_outline`
- warning → `warning_amber`
- error → `error_outline`
- audit/history → `history`
- AI → `auto_awesome` or existing project-selected AI icon
- sync/pending → `sync` / `cloud_upload_outlined`
- attachment → `attach_file`

---

# 9. Buttons

## 9.1 Primary button

### Purpose
The main action on the screen.

### Appearance
- deep brand green fill: `brandPrimaryDark`
- white text
- 8 dp radius
- 44–48 dp height
- horizontal padding 16–20 dp

### States
- default
- hover (desktop): slightly darker
- pressed: `brandPrimaryDeep`
- focused: 2 dp focus ring
- disabled: neutral disabled surface
- loading: spinner replaces or precedes label

### Examples
- Save
- Add record
- UPDATE (AI proposal)
- Sign in

## 9.2 Secondary button

Outline or soft-toned button.

- border `border`
- text `brandPrimaryDeep`
- transparent/white background
- 44–48 dp height

Examples:

- Cancel
- Filter
- Reset

## 9.3 Tertiary/text button

Use for low-risk navigation or supporting actions.

Examples:

- View all
- Clear filters
- Show details

## 9.4 Destructive button

Use only for destructive Owner operations.

- error color
- no casual use
- require confirmation for destructive actions

## 9.5 Icon button

- 40–44 dp hit target
- clear tooltip on desktop
- icon with no unlabeled mystery action

---

# 10. Inputs and forms

## 10.1 Input foundation

Every input should have:

1. label,
2. control,
3. helper/error text when needed.

Do not rely on placeholder text as the label.

## 10.2 Text input

- surface white
- 1 dp `border`
- 8 dp radius
- 44–48 dp minimum height
- 12–14 dp text
- clear focus border `brandPrimaryDark`

### States

- empty
- entered
- focused
- disabled
- error
- read-only
- protected
- computed

## 10.3 Currency input

### Purpose
Financial data entry.

### Appearance
- numeric keyboard on mobile,
- right-align the entered value where practical,
- optional `Rs.` prefix depending on renderer implementation,
- helper text never replaces label.

### Rules

- never display floating point implementation details,
- use project `Money` type,
- formatting must be deterministic,
- prevent accidental negative values where the schema disallows them.

## 10.4 Date input

Use native platform date picker.

Display format should be human-readable for the user while the wire format remains ISO/business-date driven.

Show clear contextual labels:

- `Expense date`
- `Payment date`
- `Cheque date`

## 10.5 DateTime input

Use native date + time affordances.

Separate:

- business date,
- entry timestamp

when both are relevant.

## 10.6 Select

- single-select with clear selected state
- chevron affordance
- searchable when the option set is large
- protected Select fields show lock indicator

## 10.7 Multi-select

Use chips in the selected state.

Do not turn every selected option into a new card.

## 10.8 Boolean

Prefer switch/checkbox depending on semantic meaning.

- switch → persistent on/off setting
- checkbox → item selection

## 10.9 Record reference

Reference field must:

- show the target page/entity name,
- use the target page display-column heuristic,
- allow navigation to the referenced record,
- make missing/unresolved references obvious.

Avoid displaying raw UUIDs unless no display value exists.

## 10.10 Formula

Formula fields are:

- read-only,
- visually differentiated subtly,
- accompanied by “Computed automatically” where useful.

Do not make them look disabled in a way that implies an error.

Use a neutral tinted surface and calculator/function icon if helpful.

## 10.11 Attachment

Attachments are deferred in the current release.

The design token and renderer pattern may be prepared, but no completed attachment workflow should be promoted in V1.

---

# 11. Cards, tables, lists, dialogs

## 11.1 Cards

### Purpose
Group related information without implying navigation unless clickable.

### Visual
- white surface
- 1 dp border
- 12 dp radius
- 16–20 dp padding
- minimal shadow

### States
- default
- hover/clickable
- selected
- warning
- error
- disabled

### Interaction
Entire card should only be clickable if the card represents a single destination/action. Otherwise use an explicit action.

## 11.2 Lists

Use lists for:

- page navigation,
- records on mobile,
- audit events,
- settings,
- users.

List row target: minimum 48 dp, preferably 56 dp for primary actions.

## 11.3 Tables

Desktop tables are central to the product.

### Desktop table rules

- sticky or clearly persistent header when scrolling,
- dense but readable rows,
- 44–52 dp row height,
- 12 dp horizontal cell padding minimum,
- numeric values right aligned,
- dates consistent,
- long text truncated with tooltip/detail,
- action controls at the trailing edge,
- filters above the table or in per-column controls.

### Mobile record list

Transform table rows into cards rather than forcing horizontal scrolling for ordinary use.

Card order:

1. primary/display value,
2. most important date,
3. key financial amount,
4. 1–2 supporting values,
5. status/meta,
6. overflow action.

## 11.4 Dialogs

Use dialogs for:

- destructive confirmation,
- concise confirmation,
- important disambiguation,
- focused configuration.

Do not put full workflows into dialogs.

### Dialog structure

- title,
- short explanation,
- content,
- secondary action,
- primary action.

On mobile, prefer a bottom sheet for filter/configuration and a full-screen flow for complex forms.

---

# 12. Navigation and app shell

## 12.1 Existing adaptive strategy

The project defines three responsive shells:

| Width | Layout |
|---|---|
| `< 600 dp` | bottom navigation, single pane, FAB |
| `600–1024 dp` | navigation rail, master-detail |
| `> 1024 dp` | permanent sidebar, dense grid, column filters, keyboard shortcuts, Owner AI side panel |

This is the baseline and should remain stable.

## 12.2 Mobile navigation

### Owner

`Home · Pages · + · AI · More`

### Manager

`Home · Pages · + · More`

AI must be **absent**, not greyed out, for Managers.

## 12.3 Tablet

Use a navigation rail.

Primary content can use master-detail:

- left: page/list context
- right: selected record or form

Avoid replacing the whole screen when a split view is clearer.

## 12.4 Desktop

Use a permanent sidebar.

Sidebar hierarchy:

1. Velmart brand mark
2. Home
3. Pages
4. Owner-only:
   - Users
   - Settings
   - Audit
   - AI
5. contextual page navigation or recent pages

The exact route tree remains governed by `app_router.dart` and permission guards.

## 12.5 Shell header

A desktop header should provide:

- current screen/page title,
- optional date or status context,
- search/filter controls where relevant,
- compact account/menu control.

Do not overload the header with every action.

---

# 13. Owner experience

The Owner is the system designer and data authority.

Owner UX must expose more capabilities without looking like a developer console.

## 13.1 Owner priorities

1. understand business state,
2. inspect records,
3. build/edit page structure,
4. manage people/access,
5. review audit trail,
6. ask AI questions,
7. approve AI updates.

## 13.2 Owner-only controls

Use explicit visual grouping for configuration:

- `Structure`
- `Access`
- `Data`
- `Audit`
- `AI`

Avoid scattering owner controls randomly across screens.

## 13.3 Owner editing principle

When an Owner can edit a record, show a clear edit action.

When a Manager cannot edit:

- do not show an edit action,
- do not show a disabled edit action unless the reason is genuinely useful,
- preserve view/read affordances.

---

# 14. Manager experience

Manager is an operational role.

The Manager:

- views permitted pages,
- creates records,
- uploads only where supported by the current scope,
- cannot edit existing records,
- cannot delete,
- cannot configure pages,
- cannot configure dashboard,
- cannot use AI.

## 14.1 Manager UX goal

A manager should be able to:

> Open a permitted page → tap Add → fill a small form → save → immediately continue.

## 14.2 Manager UI simplification

Remove from Manager navigation:

- AI
- page builder
- column editor
- access editor
- user management
- settings requiring Owner authority
- export

Do not leave large blank spaces where Owner controls would have been.

---

# 15. Dashboard design

## 15.1 Current product rule

The dashboard is **configurable data presentation**, not a fixed accounting dashboard.

Supported widget types:

- `METRIC`
- `TREND`
- `BREAKDOWN`
- `LIST`
- `REVIEW_QUEUE`

Existing widgets can be viewed/edited/deleted under the current plan.

The current product decision removed widget creation / Add Widget / starter suggestions from the active scope.

## 15.2 Dashboard layout

### Mobile

Single column:

1. page title,
2. as-of/context row,
3. KPI/metric cards,
4. trend,
5. breakdown/list,
6. review items.

### Tablet

Two-column card grid when card widths remain readable.

### Desktop

12-column conceptual grid:

- metrics: 3–4 columns,
- trends: 6–8 columns,
- breakdowns: 4–6 columns,
- lists/review queue: 4–6 columns.

Do not render a 12-widget wall.

## 15.3 METRIC widget

### Purpose
Answer one number quickly.

### Appearance
- label top,
- large value,
- optional period comparison,
- optional source metadata.

### Example

`Total Expenses`

`Rs. 587,400`

`September · 23 records`

### States

- loading skeleton
- loaded
- empty
- stale/offline if offline support is later implemented
- error

## 15.4 TREND widget

Use the existing `fl_chart` implementation.

Keep charts simple:

- one primary series,
- clear x-axis,
- compact labels,
- optional tooltip,
- no decorative gradients.

Use line charts or simple bars according to widget configuration.

## 15.5 BREAKDOWN widget

Current implementation uses a plain-Flutter proportional-width bar list.

Maintain:

- ranked categories,
- value,
- optional share,
- stable ordering.

Avoid forcing a pie chart when labels would become unreadable.

## 15.6 LIST widget

Use a compact list card.

Rows should show:

- display/record name,
- date/status,
- key amount,
- trailing context.

## 15.7 REVIEW_QUEUE widget

Although `needs_review` remains a real platform field, current product notes state there is no remaining code path setting it back to true.

When/if real items exist, present:

- “Needs review” title,
- record identity,
- reason/context,
- direct navigation.

Do not invent review actions beyond existing permissions.

---

# 16. Business page / table design

## 16.1 Page header

Structure:

- page name,
- optional description,
- record count/context if available,
- Search,
- Filter,
- Sort,
- Owner menu.

On Manager screens, hide owner-only configuration.

## 16.2 Table toolbar

Order:

1. search,
2. filter,
3. sort,
4. optional export for Owner,
5. owner configuration menu.

Avoid 8 small icon buttons with no labels.

## 16.3 Empty page

Message:

> No records yet.

Supporting text:

> Add the first record to start using this page.

Primary action:

`Add record`

Do not show a technical message about JSONB/schema.

## 16.4 Filtered empty state

Use different language:

> No records match these filters.

Actions:

`Clear filters`

Optional:

`Change filters`

Do not imply the page is empty.

## 16.5 Record count

Show:

- `128 records`
- or `Showing 1–50 of 128` when that information is genuinely available.

Never fabricate totals from pagination.

---

# 17. Record list, detail, create, and edit screens

## 17.1 Record list

### Purpose
Scan, search, filter, sort, and open records.

### Desktop
Dense table.

### Tablet
Master-detail.

### Mobile
Card list.

### Primary action
FAB or prominent `Add record`.

### States
- initial loading,
- refreshing,
- loaded,
- empty,
- filtered empty,
- error,
- permission denied,
- paginating.

## 17.2 Record detail

### Layout

Top:

- back,
- record display identifier,
- status if meaningful,
- Owner actions.

Body:

- grouped fields,
- financial values,
- references,
- metadata.

For ledger pages:

- make reversal/lifecycle context visible,
- never imply that a reversed row is the current active financial state.

## 17.3 Create record

### Flow

1. title + page identity,
2. dynamic fields in schema order,
3. required fields first within logical groups,
4. computed/read-only fields visually separated,
5. Save.

Use progressive grouping only when the schema is long.

### Form behavior

- validate on submit,
- show field-level errors,
- preserve entered values after validation failure,
- scroll/focus to first invalid field,
- show successful completion briefly then navigate predictably.

## 17.4 Edit record

Owner only.

Show:

- current values,
- edit affordances,
- save/cancel.

Respect optimistic locking.

If version conflict happens:

> This record changed since you opened it.

Actions:

`Reload latest`

Avoid technical wording such as “If-Match failed”.

## 17.5 Delete / void

The product uses soft deletion with reason where supported.

Confirmation should say exactly what will happen.

Example:

> Void this record?

> The record will no longer be treated as active. This action will be recorded in the audit log.

Require a reason.

---

# 18. Audit and settings screens

## 18.1 Audit screen

The Audit log is an Owner-facing operational history, not a developer console.

Current implementation is date-header-grouped and uses a filter bar with Owner-only export.

### Layout

Top:

- title `Audit`
- filter controls
- Owner export action

List:

```text
Today

11:25  Aathi changed Kasun's Basic Salary in Staff
       from Rs.45,000 to Rs.55,000 · via AI

10:42  Manager 1 added a record to Expenses
       Rs.35,000 · Repair
```

### Plain sentence principle

The primary line must be understandable without database knowledge.

Avoid exposing:

- UUIDs,
- SQL,
- internal endpoint names,
- JSON blobs,
- hash values in the normal UI.

A technical detail can exist in secondary detail UI if a future support workflow requires it.

## 18.2 Audit filter

Supported conceptual dimensions:

- user,
- page,
- entity,
- date,
- source.

Use filter chips or a filter sheet rather than five permanent dropdowns on mobile.

## 18.3 Settings

Settings are Owner-only.

Group into:

- Company
- Users & access
- Data
- Dashboard
- AI
- Security / session

Never create a flat 20-item list.

## 18.4 Users

User list:

- name,
- role,
- active/inactive state,
- store assignment where relevant,
- last useful status.

Owner actions:

- add user,
- edit,
- deactivate,
- role change.

Do not expose security implementation details such as token version.

## 18.5 Stores

The V1 deployment is one supermarket, but schema supports store assignments.

Keep store UI simple:

- store name,
- status,
- assigned managers.

Do not build a multi-store management dashboard when there is one store.

---

# 19. AI interface design

## 19.1 Product role

AI is not the source of truth.

UI principle:

> **AI explains and proposes; Velmart verifies and the Owner decides.**

## 19.2 Access

AI is Owner-only.

It must be absent from Manager navigation.

## 19.3 Chat screen

### Desktop

AI panel can sit beside the table.

Left/center:

- business data table

Right:

- AI conversation

This lets the Owner ask:

> How much did we spend on electricity this month?

while keeping the underlying table visible.

### Mobile

Full-screen chat.

Use clear links back to source page/records.

## 19.4 Message bubble

### User
- subtle brand/neutral tint,
- right aligned or standard chat layout,
- concise.

### AI
- neutral white/surface,
- left aligned,
- structured data-first answer.

Avoid excessive chat bubbles.

## 19.5 Provenance

Every important numeric answer should show provenance.

Example:

> **Rs. 587,400**

> 23 records in Expenses · 1–30 September

Make provenance visually visible but secondary.

## 19.6 Tool activity chip

Use compact status chips such as:

- `Finding pages`
- `Checking Expenses`
- `Calculating total`

These should communicate system progress without exposing developer implementation details.

## 19.7 Refusal

When AI cannot answer:

> I couldn't find a page containing that information.

Supporting:

> You currently don't have a table that records it.

Do not hallucinate.

## 19.8 Ambiguous question

When multiple pages can answer:

> I found two possible sources.

Then list:

- Expenses
- Vehicle Costs

and ask the Owner to choose.

## 19.9 Proposed update card

This is the most trust-sensitive AI component.

### Purpose

Show the exact server-computed diff before an Owner update.

### Appearance

- strong but restrained header,
- expiry indicator,
- record identity,
- before → after diff,
- computed downstream values,
- provenance,
- audit note,
- Cancel and UPDATE.

### Example

```text
PROPOSED UPDATE                         expires 9:41

Staff · Kasun Perera · Sep 2026

Basic Salary
Rs.45,000  →  Rs.55,000

Net Salary
Rs.52,300  →  Rs.62,300
Computed automatically

Source: AI · Session #a3f9

This change will be recorded in the audit log.

[Cancel]                         [UPDATE]
```

### States

- pending
- applying
- applied
- expired
- cancelled
- stale/version-conflict
- failed

### Expired

> This update expired.

Action:

`Ask AI again`

### Stale

> This record changed after the proposal was created.

Action:

`Create a new proposal`

Never silently apply a stale proposal.

## 19.10 Blast radius

For proposals affecting more than five records:

- show a clear bulk-change warning,
- list individual affected records,
- add per-item selection if the implementation supports it,
- keep UPDATE visually dominant but not dangerous.

---

# 20. Loading, empty, success, warning, error states

## 20.1 Loading

Prefer skeletons for dashboard cards and tables.

Use a progress indicator for:

- form submit,
- export generation,
- AI processing,
- route-level blocking actions.

Do not spin infinitely without contextual text.

## 20.2 Empty

Use:

- one icon,
- one headline,
- one short explanation,
- one primary action.

Example:

> No records yet  
> Add the first record to this page.

## 20.3 Success

Use a short snackbar/toast for transient completion.

Examples:

- `Record saved`
- `Export ready`
- `Changes applied`

Do not require users to dismiss success messages.

## 20.4 Warning

Use amber only when user attention is needed.

Examples:

- reconciliation difference,
- potentially risky schema narrowing,
- protected field context,
- stale-looking dashboard data.

## 20.5 Error

Errors must say:

1. what failed,
2. whether the user can retry,
3. whether data was saved.

Example:

> Couldn’t save this record.

> Check the highlighted fields and try again.

Retry when appropriate.

## 20.6 Permission denied

Do not expose backend implementation.

Use:

> You don't have permission to do that.

For a Manager encountering an Owner-only concept because of a deep link, provide a safe back action.

---

# 21. Responsive/adaptive layouts

## 21.1 Breakpoints

Honor the existing project strategy:

### Compact `< 600 dp`

- bottom navigation,
- single pane,
- FAB for primary create,
- cards instead of tables,
- bottom sheets for filters,
- full-screen forms,
- simplified action bars.

### Medium `600–1024 dp`

- navigation rail,
- master-detail,
- two-column forms where useful,
- dialogs/sheets for focused utilities.

### Expanded `> 1024 dp`

- persistent sidebar,
- dense grid,
- keyboard-friendly navigation,
- column filters,
- side-panel forms,
- Owner AI side panel.

## 21.2 Do not design three separate apps

Use the same information hierarchy.

Only the container changes.

Bad:

- different wording by platform,
- different record fields,
- different business actions.

Good:

- same data,
- same permissions,
- different layout density and navigation.

## 21.3 Form adaptation

Mobile:

- one column,
- 16 dp margins,
- full-width controls.

Tablet:

- 1–2 columns.

Desktop:

- 2–3 logical columns depending on field type and form length.

Do not put currency fields and long descriptions in equal-width columns when their content needs differ.

## 21.4 Table adaptation

Desktop:

`Data grid`

Tablet:

`Master-detail`

Mobile:

`Record cards`

Do not force users to horizontally scroll across a ten-column business record simply because the desktop grid exists.

---

# 22. Accessibility guidelines

## 22.1 Touch targets

Minimum 44 × 44 dp for interactive controls.

## 22.2 Contrast

Aim for WCAG 2.2 AA contrast.

Important:

- white text must not be placed on the bright logo green when contrast is insufficient,
- use `brandPrimaryDark` / `brandPrimaryDeep` for filled actions.

## 22.3 Focus

Every interactive element must have a visible focus state.

Focus ring:

- 2 dp,
- brand-based,
- not dependent on hover.

## 22.4 Screen readers

All icon-only controls require semantics/tooltip labels.

Examples:

- `Open filters`
- `Export audit log`
- `More actions`

## 22.5 Motion

Avoid decorative animations.

Use short transitions for:

- navigation,
- expanding/collapsing,
- save confirmation.

Never use animation as the only communication of status.

## 22.6 Language

Use business language.

Avoid:

- `CRUD`
- `JSON`
- `RLS`
- `JWT`
- `schema mutation`

unless the user is explicitly in a technical/support context.

---

# 23. Flutter implementation guidelines

## 23.1 Theme architecture

Centralize tokens in the existing `lib/core/theme/` area.

Recommended conceptual structure:

```text
lib/core/theme/
├── app_colors.dart
├── app_typography.dart
├── app_spacing.dart
├── app_radii.dart
├── app_theme.dart
└── app_component_themes.dart
```

Do not copy hex values throughout feature screens.

## 23.2 Theme ownership

`ThemeData` should own:

- ColorScheme
- text theme
- input decoration
- button themes
- card theme
- dialog theme
- chip theme
- navigation theme
- divider theme

Feature widgets should consume theme tokens.

## 23.3 Avoid hard-coded layout values

Good:

```dart
padding: const EdgeInsets.all(AppSpacing.md)
```

Avoid:

```dart
padding: const EdgeInsets.all(17)
```

unless the value has a documented reason.

## 23.4 Field renderers

The project already uses the field-renderer architecture.

Design requirement:

> **One column type = one renderer contract + one visual language.**

All renderers must share:

- label,
- helper/error area,
- focus treatment,
- required treatment,
- read-only treatment,
- spacing,
- typography.

## 23.5 Money

Use:

- `Money`
- `AmountText`

Never introduce a separate money formatting helper inside a screen.

Never use `double` for money.

## 23.6 Permissions

The client permission helper is a UI hint only.

UI pattern:

```text
server permission → application state → capability hint → UI
```

Never:

```text
button hidden → assumed secure
```

The server remains authoritative.

## 23.7 Routing

Use `go_router` and existing guards.

Screen design should not create direct navigation paths that bypass the route architecture.

## 23.8 State management

Use Riverpod as the state boundary.

Screen widgets should:

- read state,
- render state,
- dispatch user intent.

Avoid embedding networking or repository calls directly in leaf widgets.

## 23.9 Adaptive shell

Keep all shell breakpoints in one place.

`adaptive_scaffold.dart` should remain the single composition boundary for:

- bottom navigation,
- navigation rail,
- sidebar.

Do not duplicate width logic in every screen.

## 23.10 Tables and cards

Use shared primitives for:

- data table rows,
- mobile record cards,
- status chips,
- action menus,
- money cells,
- date cells.

The same data should render consistently in all modes.

---

# 24. Reusable component and design-token structure

## 24.1 Shared primitives

The existing shared-widget direction includes:

- `adaptive_scaffold.dart`
- `amount_text.dart`
- `sync_badge.dart`
- `empty_state.dart`

The design system should extend this same foundation rather than creating a parallel design layer.

## 24.2 Recommended reusable components

```text
core/widgets/
├── adaptive_scaffold.dart
├── amount_text.dart
├── empty_state.dart
├── sync_badge.dart
├── app_button.dart
├── app_card.dart
├── app_section.dart
├── app_text_field.dart
├── app_date_field.dart
├── app_select_field.dart
├── app_status_chip.dart
├── app_error_state.dart
├── app_loading_state.dart
├── app_filter_bar.dart
├── app_data_table.dart
├── app_record_card.dart
├── app_confirm_dialog.dart
└── app_page_header.dart
```

Do not add every component immediately. Extract a shared component when two or more screens clearly need the same behavior.

## 24.3 Component contract

For every reusable component define:

### Purpose
What problem does it solve?

### Variants
What visual/behavioral versions exist?

### States
Default, focused, disabled, loading, success, warning, error, selected, etc.

### Content
What data does it receive?

### Interaction
What callbacks/events does it expose?

### Responsive behavior
How does it change across compact/medium/expanded widths?

### Accessibility
Semantics, labels, focus order, hit area.

---

# 25. Screen-by-screen UI guidelines

This section maps directly to the current implementation surface and the project structure.

## 25.1 `lib/features/auth/` — Login

### Purpose
Authenticate Owner/Manager.

### Visual
- clean neutral background,
- centered logo,
- compact login card,
- minimal fields,
- strong primary `Sign in`.

### Spacing
- 24 dp card padding,
- 16 dp field spacing,
- 24 dp action spacing.

### States
- idle,
- submitting,
- invalid credentials,
- locked out,
- network error.

### Rules
- never reveal whether an account exists,
- do not add unnecessary onboarding,
- preserve platform-appropriate keyboard behavior.

---

## 25.2 `home_screen.dart` — Dashboard/home

### Purpose
Give the user an immediate business overview.

### Current implementation
P5 dashboard implementation renders widgets, including `TREND` using `fl_chart` and `BREAKDOWN` using proportional-width bars.

### Design
- clear `Home` title,
- compact context,
- dashboard widgets,
- role-aware visibility.

### Owner
Can access Owner dashboard controls supported by the current product scope.

### Manager
Sees only permitted/visible widgets from permitted pages.

---

## 25.3 `page_list_screen.dart`

### Purpose
Show available business pages.

### Layout
Page title + search/optional filter + list/grid.

### Item
- page icon/mark,
- page name,
- optional description,
- optional record count,
- trailing arrow.

### Owner
May see configuration menu where authorized.

### Manager
Only permitted pages exist in this view.

### Empty
If no custom pages exist but shipped system pages exist, do not describe the workspace as empty.

---

## 25.4 `record_list_screen.dart`

### Purpose
Primary data browsing surface.

### Desktop
Dense grid.

### Mobile
Cards.

### Existing implementation
CSV export is wired to OS share sheet in the current implementation history.

Current scope says export remains Owner-only.

### Design rule
Do not combine filter, sort, export, schema configuration, and record actions into one overloaded toolbar.

---

## 25.5 `record_detail_screen.dart`

### Purpose
Inspect a single record.

### Existing behavior
The implementation includes a dedicated protected-field change action for Owner use.

### Design
- record identity at top,
- grouped fields,
- important values emphasized,
- protected value shown with lock marker,
- Owner actions in overflow/menu.

### Protected field change
Use a focused dialog/sheet:

`Change Status`

Then show:

`PENDING → PAID`

and explicit confirmation.

---

## 25.6 `record_form_screen.dart`

### Purpose
Dynamic create form driven by page schema.

### Existing architecture
Form fields are generated from page schema and use type-specific renderers.

### Design
- field order from schema position,
- consistent labels,
- required marker,
- helper text,
- computed fields visually separated,
- protected Manager values not editable.

### Mobile
Single column.

### Desktop
Responsive multi-column grouping without breaking logical order.

---

## 25.7 `filter_sheet.dart`

### Purpose
Filter records without cluttering the main list.

### Mobile
Bottom sheet.

### Tablet/desktop
Dialog/popover or toolbar panel depending on width.

### Filter patterns
- equality,
- ranges,
- contains,
- null checks,
- multi-value selection.

Do not expose the internal operator names (`eq`, `gte`, etc.) to ordinary users.

Use human language:

- `Equals`
- `Greater than`
- `Between`
- `Contains`
- `Is empty`

---

## 25.8 `page_builder_screen.dart`

### Purpose
Owner creates a business page/table.

### Core UX

Step-like mental model without creating unnecessary wizard state:

`Page details → Columns → Review → Save`

The Owner should always see the resulting table structure.

### Header
`Create page`

### Page name
Large primary input.

### Description
Short optional explanation.

### Columns
Each column row shows:

- display name,
- type,
- required/optional,
- protected where applicable,
- indexed if the platform exposes this choice,
- order.

### Interaction
`Add column` should be visually obvious.

### Scope note
The plan later removed validation rules and dashboard widget creation; do not reintroduce those as page-builder tabs.

---

## 25.9 `column_editor_screen.dart`

### Purpose
Owner defines/edit a column.

### Fields
Depending on type:

- name,
- type,
- required,
- options,
- protected,
- formula,
- reference target,
- constraints supported by current schema.

### Formula
Use a structured editor with a visible formula preview/result context where safely supported, but do not invent a client-side evaluator if current implementation intentionally relies on server calculation.

### Schema evolution warning
For risky narrowing/removal operations, make the consequence explicit and require confirmation.

---

## 25.10 `access_editor_screen.dart`

### Purpose
Owner grants Manager page access.

### Design
Use a list of Managers and permission toggles per page.

Prefer wording:

- `Can view`
- `Can add records`

rather than raw API names such as `view_access` / `create_access`.

### Empty/default
New pages start with no Manager access.

Explain:

> Managers won't see this page until access is granted.

This is safer than a hidden default.

### Current implementation note
The implementation plan recorded a backend gap around reading current page grants before replacing them. The design should not imply unsupported granular retrieval if the current API still lacks it.

---

## 25.11 `validation_editor_screen.dart`

### Current status
Historical implementation code exists according to the implementation record, but the latest locked plan removed `page_validations`, its endpoints, and client editor.

### Design rule
Do not expose this screen in the active V1 navigation or workflow.

Treat it as deprecated/historical until code cleanup occurs.

---

## 25.12 Reconciliation screen

### Purpose
Show Daily Revenue vs Cash Ledger by business date.

### Primary visual

```text
1–30 September

Date        Revenue        Ledger       Difference
Sep 01      Rs.250,000     Rs.248,000   Rs.2,000
Sep 02      Rs.275,000     Rs.275,000   Rs.0
```

### Status

- zero difference → success
- non-zero → warning/error emphasis
- missing side → explicit neutral/informational indicator

### Detail

Selecting a day can show:

- Daily Revenue
- Cash Ledger
- difference

Do not hide the difference.

---

## 25.13 CSV export surface

### Current scope
CSV export remains Owner-only.

### UX
Use:

`Export`

not:

`POST /exports`

Show filters applied before export if available.

Success:

> Export ready.

Then hand off to the OS share sheet as the current implementation does.

---

## 25.14 Import screens

CSV import was removed from current product scope.

Do not build new visual patterns around import.

If legacy routes still exist in code, treat them as deprecated and do not add them to navigation.

---

## 25.15 `audit_screen.dart`

### Purpose
Plain-language history.

### Current implementation
Date-header grouping + filter bar + Owner-only export.

### Design
Preserve this architecture.

Do not replace with a complicated audit table.

---

## 25.16 `widget_builder_screen.dart`

### Current scope reconciliation
The implementation record says this file was expanded into a real form. The latest product plan, however, removed widget creation and “Add widget”.

### Design rule
Do not expose Widget Builder as a normal V1 create flow.

If existing code still needs the screen for internal compatibility:

- keep visual treatment consistent with the dashboard,
- clearly distinguish legacy code from current product navigation,
- do not invent a new dashboard creation journey.

---

## 25.17 `ai_chat_screen.dart`

### Current status
Planned for P7, not yet started.

### Design target
- Owner-only,
- desktop side panel,
- mobile full screen,
- provenance-first,
- tool activity chips,
- proposal cards,
- no fake “typing” theatrics.

---

## 25.18 `message_bubble.dart`

### Rules

AI messages:

- readable line length,
- structured headings,
- compact tables where appropriate,
- money formatted via standard money component,
- source/provenance shown.

User messages:

- visually distinct but not oversized.

---

## 25.19 `proposal_card.dart`

### Rules

This is a high-trust component.

- never hide old value,
- never hide new value,
- highlight affected fields,
- show computed downstream effects,
- show expiry,
- show audit statement,
- one primary UPDATE action.

---

## 25.20 `tool_activity_chip.dart`

### Rules

User language:

`Checking Expenses`

instead of:

`aggregate_records(page_key=expenses...)`

The architecture remains generic; the UI should remain human.

---

## 25.21 `adaptive_scaffold.dart`

This is a foundation component, not a page feature.

Responsibilities:

- determine width class,
- choose shell,
- preserve navigation state,
- render correct role navigation,
- maintain consistent app-bar behavior.

All screens must fit inside it cleanly.

---

## 25.22 `amount_text.dart`

Canonical financial display.

Responsibilities:

- LKR formatting,
- consistent alignment where used,
- semantic accessibility label,
- positive/zero/negative handling where supported.

Never create a second financial text renderer casually.

---

## 25.23 `empty_state.dart`

Canonical structure:

- icon,
- title,
- message,
- optional primary action.

Keep it compact.

---

## 25.24 `sync_badge.dart`

Offline is deferred in the current release, so this should not be used to imply that offline mode is live.

When offline support resumes, the design target is:

- amber pending state,
- explicit `Pending sync`,
- page banner such as `3 records not yet synced`,
- failed state with reason.

Silence about unsynced business data is unacceptable.

---

# 26. Design rules Claude Code must follow

These are implementation guardrails for every future UI change.

## 26.1 Scope guardrails

1. Do not invent a new product module when an existing page-engine screen can support the requirement.
2. Do not reintroduce removed V1 features because a legacy file still exists.
3. Do not add Suppliers, Employees, Card Settlements, or other fixed modules as developer-owned sections; these are Owner-created pages.
4. Do not create a separate screen pattern for each financial table when the page engine already provides one generic pattern.

## 26.2 Architecture guardrails

1. Use existing feature-first structure.
2. Keep routing in `lib/routing/`.
3. Use existing Riverpod state architecture.
4. Use the repository/service boundaries already established.
5. Do not put direct HTTP/database calls inside presentation widgets.
6. Use `adaptive_scaffold.dart` for responsive shell behavior.
7. Reuse existing domain objects and providers.

## 26.3 Theme guardrails

1. Use the design tokens from the central theme.
2. Never hard-code brand HEX values in leaf screens.
3. Use deep green for primary filled actions, not bright logo green when contrast fails.
4. Keep semantic colors reserved for semantic states.
5. Avoid gradients for normal business controls.

## 26.4 Component guardrails

1. Reuse `AmountText` for money.
2. Reuse `EmptyState` for empty states.
3. Use one renderer per column type.
4. Preserve consistent field spacing.
5. Keep action hierarchy obvious.
6. Avoid introducing a button style that exists nowhere else.

## 26.5 Responsive guardrails

1. Honor `<600`, `600–1024`, and `>1024` behavior.
2. Never make mobile a shrunken desktop.
3. Never introduce horizontal scrolling for a normal form.
4. Use cards for mobile record lists.
5. Keep desktop grid density high but readable.

## 26.6 Role guardrails

1. Owner has full business/data control.
2. Manager creates but does not edit/delete records.
3. Managers cannot configure schema.
4. Managers cannot configure dashboard.
5. Managers cannot export.
6. AI is Owner-only and absent from Manager navigation.
7. UI permission checks are hints only; backend remains authoritative.

## 26.7 Financial guardrails

1. Never use `double` for money.
2. Never display approximate monetary values unless the user explicitly asks for approximation.
3. Keep numeric columns right aligned in tables.
4. Do not hide reconciliation differences.
5. Do not visually imply that computed formula values are manually editable.

## 26.8 AI guardrails

1. AI answers must show provenance when presenting material figures.
2. AI must not visually appear to have direct database authority.
3. AI proposals must show server-computed before/after state.
4. UPDATE is the sole confirmation.
5. Never auto-apply a proposal.
6. Never hide stale/expired status.
7. Never make an Owner believe an AI answer is verified merely because it has confident wording.

## 26.9 Error-handling guardrails

1. Preserve form input after validation failures.
2. Use human-readable error messages.
3. Do not expose stack traces.
4. Show retry only where retry is meaningful.
5. Distinguish empty data from failed data.

## 26.10 Accessibility guardrails

1. Minimum 44 dp touch target.
2. Visible keyboard focus.
3. Icon buttons need labels/tooltips.
4. Do not use color as the only state indicator.
5. Ensure important text meets contrast requirements.

---

# 27. Major component specification matrix

| Component | Purpose | Default surface | Primary state | Error state | Mobile behavior |
|---|---|---|---|---|---|
| PrimaryButton | Main action | deep green | white text | error only when action fails | full width where useful |
| SecondaryButton | Secondary action | white/outline | green text | neutral | full width or inline |
| TextField | Text entry | white | green focus border | red border + message | full width |
| CurrencyField | Money entry | white | numeric input | red field state | numeric keyboard |
| DateField | Date entry | white | standard focus | red helper | native picker |
| SelectField | Controlled choice | white | selected option | invalid selection | sheet/popup |
| RecordRef | Related record | white | resolved reference | unresolved warning/error | picker sheet |
| FormulaField | Computed value | subtle neutral tint | read-only | error from source data only | full width |
| StatusChip | Lifecycle/state | semantic tint | text + icon | error/warning | compact |
| AppCard | Group content | white | default | semantic variant | full width |
| DataTable | Dense desktop data | white | row hover/focus | table-level error | cards below 600dp |
| RecordCard | Mobile data row | white | tap feedback | semantic row | full width |
| EmptyState | No data | background | icon + action | — | centered |
| ErrorState | Failed state | background | retry | explicit message | centered |
| FilterBar | Query control | surface | active chips | invalid filter | bottom sheet |
| AuditRow | History | transparent/white | timestamp + sentence | failed action semantic | stacked |
| MetricWidget | KPI | white | large number | widget error state | full width |
| TrendWidget | Trend | white | chart | widget error | full width/2-col |
| BreakdownWidget | Ranked distribution | white | bars + values | widget error | full width |
| ListWidget | Record shortlist | white | compact rows | widget error | full width |
| ProposalCard | AI approval | white + accent border | pending | stale/expired | full screen/card |
| ToolActivityChip | AI progress | neutral | compact status | error variant | inline |

---

# 28. Information hierarchy by screen type

## 28.1 Operational screen

Priority order:

1. what page am I on?
2. what data is here?
3. what can I do?
4. what needs attention?

## 28.2 Configuration screen

Priority order:

1. what am I configuring?
2. what will change?
3. what is valid?
4. how do I save?

## 28.3 Financial review screen

Priority order:

1. amount,
2. comparison,
3. difference/exception,
4. source records,
5. action.

## 28.4 AI screen

Priority order:

1. answer,
2. provenance,
3. uncertainty/limits,
4. proposed change if any,
5. confirmation.

---

# 29. Content and microcopy rules

## 29.1 Prefer

- `Add record`
- `Save`
- `Cancel`
- `Export`
- `Clear filters`
- `Change Status`
- `No records yet`
- `No records match these filters`
- `This record changed since you opened it`
- `This update expired`

## 29.2 Avoid

- `Execute`
- `Mutate`
- `CRUD`
- `Submit payload`
- `POST`
- `409 conflict`
- `Schema violation`
- `Permission matrix`
- `RLS policy`
- `JSONB`

unless the screen is explicitly an engineering/support surface.

---

# 30. Data-density rules

## Mobile

One card should communicate the record in under 2 seconds.

Maximum default content:

- 1 primary title,
- 1 amount/date line,
- 2 supporting values,
- 1 status,
- 1 action area.

## Tablet

Use master-detail to minimize navigation.

## Desktop

Data density may increase, but:

- preserve 44 dp-ish row readability,
- freeze important context,
- keep amounts aligned,
- avoid giant empty columns.

---

# 31. Motion and interaction

Use motion only to communicate structure.

Approved patterns:

- subtle route fade/slide,
- sheet slide-up,
- card hover elevation,
- save confirmation,
- skeleton shimmer if already supported.

Avoid:

- decorative logo animations,
- bouncing buttons,
- continuous dashboard movement,
- fake AI typing for long periods,
- parallax.

Target ordinary interaction feedback in roughly 100–250 ms.

---

# 32. Security-sensitive UI behavior

The UI must reinforce the system's security model without exposing implementation details.

### Protected field

Display:

`Status  🔒`

Helper:

`Only an Owner can change this value.`

### Manager-only view

Do not display Owner actions at all.

### Audit

Show:

`via AI`

where the source is AI.

### Stale action

Show a direct, understandable explanation.

Do not say:

`ETag mismatch`.

---

# 33. Design QA checklist

Before merging a UI change, Claude Code should verify:

### Visual

- correct token usage,
- consistent spacing,
- correct typography,
- no accidental color introduction,
- no unnecessary shadows,
- no broken logo treatment.

### Functional

- current route still works,
- permission behavior remains correct,
- primary action works,
- errors preserve context,
- loading states terminate,
- empty states are distinct from error states.

### Responsive

- `<600 dp` tested,
- `600–1024 dp` tested,
- `>1024 dp` tested,
- no overflow,
- no clipped actions,
- no unreadable table cells.

### Accessibility

- semantics,
- focus,
- contrast,
- hit targets,
- icon labels.

### Product scope

- no removed module reintroduced,
- no Manager-only restriction bypass,
- no AI exposure to Manager,
- no offline feature implied as live,
- no attachment feature implied as live.

---

# 34. Definition of visual done

A screen is visually complete when:

1. It uses the Velmart token system.
2. It clearly exposes one primary action.
3. It has complete loading/empty/success/warning/error behavior.
4. It works at all three responsive widths.
5. It respects Owner/Manager capabilities.
6. It reuses established components where possible.
7. It does not expose technical implementation details to business users.
8. Financial values are visually precise.
9. Accessibility requirements are met.
10. A non-technical supermarket user can understand the screen without developer explanation.

---

# 35. Recommended implementation order

To minimize design drift:

### Stage 1 — Foundation

1. `app_colors.dart`
2. `app_typography.dart`
3. `app_spacing.dart`
4. `app_radii.dart`
5. `app_theme.dart`

### Stage 2 — Core primitives

1. buttons
2. fields
3. cards
4. chips
5. page header
6. loading/empty/error states
7. data table
8. record card

### Stage 3 — Shell

1. `adaptive_scaffold.dart`
2. Owner navigation
3. Manager navigation
4. role-aware menu structure

### Stage 4 — Core business screens

1. home/dashboard
2. page list
3. record list
4. record detail
5. record form
6. filters
7. reconciliation
8. audit

### Stage 5 — Owner configuration

1. page builder
2. column editor
3. access editor
4. user/settings surfaces

### Stage 6 — Future AI

1. AI chat
2. provenance
3. tool activity
4. proposal card
5. stale/expired states

---

# 36. Final design direction

Velmart should look like a **calm, green-led business operating system**.

The logo contributes:

- fresh green as the core brand,
- blue/teal as an analytical secondary accent,
- strong geometric symmetry,
- a recognizable central mark.

The application translates that into:

- white and soft-neutral surfaces,
- deep green primary actions,
- quiet blue/teal analytical accents,
- strong dark text,
- subtle borders,
- restrained elevation,
- highly consistent forms and tables,
- clear state communication,
- and adaptive layouts that prioritize the user's current job.

The defining interaction pattern is:

> **Open → Understand → Act → Confirm → Continue**

For records:

> **Page → Search/Filter → Record → Save**

For Owner configuration:

> **Page → Columns → Review → Save**

For reconciliation:

> **Date → Revenue vs Ledger → Difference → Investigate**

For AI:

> **Ask → Verify provenance → Review diff → UPDATE**

For every future UI change:

> **Preserve the architecture, preserve the permissions, preserve the data truth, and make the next action obvious.**

---

# 37. Source-of-truth verification notes

This handoff is intentionally aligned with the latest available implementation inventory and locked project plan.

The implementation plan states that:

- P1–P5 client code is compiler-verified;
- the page engine client includes the page/record/form/filter/builder/access surfaces;
- the adaptive shell follows the 600/1024 dp breakpoints;
- the dashboard currently renders `TREND` and `BREAKDOWN` widgets;
- Audit is implemented with date-grouped entries, filtering, and Owner-only export;
- attachments are deferred;
- offline support is deferred;
- AI read/write are not started.

The locked project plan states that:

- the application has exactly two roles, Owner and Manager;
- there are six shipped business pages;
- all other business structures are Owner-created pages;
- Managers can create records but cannot edit/delete;
- AI is Owner-only;
- dashboard widgets are viewable/configurable within the current scope but widget creation was removed;
- CSV export remains;
- page validation rules were removed.

No new application module has been introduced by this design document.

The direct GitHub repository URL supplied for the codebase could not be fetched from this execution environment. Therefore, this document uses the **current code inventory and verification statements contained in `IMPLEMENTATION_PLAN(4).md` as the grounded codebase representation**, rather than inventing unseen implementation details. The file-level screen guidance above is therefore limited to what the supplied implementation records establish, with product-scope decisions resolved by the newer locked plan.

