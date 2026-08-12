# Test checklist and Saturday presentation flow

## Test tomorrow

1. Start the server and create the administrator account.
2. Add a product called `Amoxicillin 500mg`, category `Medicines`, barcode `1234567890123`, unit `capsules`, reorder level `25`.
3. Receive Batch `AMX-SEP` with 40 capsules and an expiry date within the next 20 days.
4. Receive Batch `AMX-DEC` with 80 capsules and an expiry date more than 60 days away.
5. Confirm the dashboard shows the first batch in the expiry queue.
6. Scan or type `1234567890123` in Barcode scanner; it should open Amoxicillin.
7. Issue 50 capsules through **Issue stock (FEFO)**. Confirm the first batch becomes 0 and the second batch becomes 70. This proves FEFO.
8. Add a product with reorder level 30 and only 10 units. Confirm it appears in Alerts.
9. Open Analytics and confirm categories, stock value, and issued-product data appear.
10. Open Audit log as administrator and confirm actions are recorded.
11. Click Export CSV and confirm a file downloads.

## 3-minute presentation

1. **Problem (20 sec):** Expired stock causes losses and unsafe use; manual stock records make accountability difficult.
2. **Dashboard (30 sec):** Show the live stock overview, low-stock warnings, and the expiry-prevention queue.
3. **Batch control (40 sec):** Open a product and show two batches with different expiry dates.
4. **FEFO (45 sec):** Issue stock. Explain that the earliest safe expiry batch is automatically selected before newer stock.
5. **Barcode and Wi-Fi (25 sec):** Scan a barcode to locate a product. Explain that staff can use a tablet or phone on the shop Wi-Fi with the computer's local address.
6. **Accountability and insight (30 sec):** Show Analytics and Audit log, highlighting operational decisions and traceability.
7. **Future integrations (20 sec):** CSV export is ready now; POS, supplier, email, SMS/WhatsApp, and cloud hosting are planned integration points.

## Important presentation note

For a live demo, run the system before the presentation and keep its terminal window open. Use the same Wi-Fi for any phone/tablet test. Do not expose this local development server to the public internet.
