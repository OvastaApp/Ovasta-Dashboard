# Ovasta Dashboard

Daily business metrics for **Ovasta**, the grocery delivery service, shown on a lightweight static dashboard hosted on GitHub Pages.

> ⚠️ **Internal use only.** This dashboard contains business performance data. Please don't share the link outside the Ovasta team.

## What's inside

| Section | What it shows |
|---|---|
| **Last working day** | Orders placed, delivered, cancelled and open, plus GMV and NMV for the latest full working day, by district and by hour |
| **Key metrics** | Monthly orders, GMV, NMV, average order value, delivery fees, active customers and cancellation rate, with month-over-month change |
| **Monthly trend** | Orders, GMV/NMV, active customers and order-type mix over time |
| **District comparison** | Each district's share of orders and NMV for the selected month |
| **Complaints** | Support tickets by type (delay, missing/wrong items, product quality, pricing, courier behavior, app and other), solved rate, and tickets per 100 delivered orders |
| **Low ratings** | Rating distribution and the main reasons behind ratings of 3★ or lower |
| **Monthly table** | Full month-by-district breakdown |

The **Month** and **District** filters at the top drive every section. Data starts from **February 2026**, and all amounts are in **EGP**.

## Metric definitions

- **Orders placed**: every order created in the period.
- **GMV** (Gross Merchandise Value): the goods value of all placed orders, before cancellations. Delivery fees are not included.
- **NMV** (Net Merchandise Value): the goods value of **delivered** orders after discounts and adjustments.
- **AOV** (average order value): NMV divided by delivered orders.
- **Cancellation rate**: cancelled orders divided by placed orders.
- **Active customers**: distinct customers with at least one delivered order.
- **Growth**: month-over-month % change, calculated on full months only. The current month is compared by daily pace.

Complaint types for new tickets are assigned automatically from keywords in the ticket text. Tickets that don't clearly fit a type go to "Other".

## How it updates

The data refreshes **every day at 07:00 Cairo time**:

1. A scheduled job runs a **read-only** query against the production database. It only reads, never writes, and uses short timeouts.
2. The results are combined into `data.json`. No customer names, phone numbers or ticket text are included.
3. The new `data.json` is committed and pushed here, and GitHub Pages publishes it automatically.

If any step fails, nothing is pushed and the previous day's dashboard stays online.

## Files

```
index.html        Dashboard page
assets/app.js     Charts, filters and rendering
assets/style.css  Styling
data.json         Aggregated metrics (updated daily)
```

## Run locally

```bash
python -m http.server 8000
# then open http://localhost:8000
```
