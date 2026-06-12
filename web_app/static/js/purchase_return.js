(function () {
    function n(value) {
        return Number(value || 0) || 0;
    }

    function money(value) {
        return n(value).toFixed(2);
    }

    function esc(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function urlFromTemplate(template, id) {
        return String(template || "").replace("/0/", `/${id}/`);
    }

    function taxEnabled() {
        return Array.from(document.querySelectorAll("#purchase-return-items thead th"))
            .some((th) => th.textContent.trim() === "Tax %");
    }

    function calculateLine(row) {
        const quantityInput = row.querySelector('[name="quantity"]');
        const maxQty = n(quantityInput?.getAttribute("max"));
        let quantity = n(quantityInput?.value);
        if (maxQty > 0 && quantity > maxQty) {
            quantity = maxQty;
            quantityInput.value = money(maxQty);
        }
        const rate = n(row.querySelector('[name="purchase_rate"]')?.value);
        const taxPercent = n(row.querySelector('[name="tax_percent"]')?.value);
        const base = quantity * rate;
        const tax = base * taxPercent / 100;
        const total = base + tax;
        const totalInput = row.querySelector(".pr-line-total");
        if (totalInput) totalInput.value = money(total);
        return total;
    }

    function recalcAll() {
        let total = 0;
        document.querySelectorAll("#purchase-return-items tbody tr").forEach((row) => {
            total += calculateLine(row);
        });
        const display = document.querySelector("#purchase-return-total");
        if (display) display.textContent = money(total);
    }

    function rowHtml(item) {
        const maxQty = item.max_returnable_qty || item.max_quantity || item.quantity || "0";
        return `
            <tr>
                <td>
                    <input type="hidden" name="item_service_id" value="${esc(item.item_id || item.item_service_id)}">
                    <input type="hidden" name="supplier_purchase_item_id" value="${esc(item.purchase_item_id || item.supplier_purchase_item_id)}">
                    <input class="form-control" name="description" value="${esc(item.description || item.item_name)}" readonly>
                </td>
                <td><input class="form-control" value="${esc(item.purchased_qty || item.quantity || "0")}" readonly></td>
                <td><input class="form-control" value="${esc(item.already_returned_qty || "0")}" readonly></td>
                <td><input class="form-control" value="${esc(maxQty)}" readonly></td>
                <td><input class="form-control pr-calc" type="number" step="0.01" min="0.01" max="${esc(maxQty)}" name="quantity" value="${esc(maxQty)}"></td>
                <td><input class="form-control pr-calc" type="number" step="0.01" min="0" name="purchase_rate" value="${esc(item.rate || item.purchase_rate || "0")}" readonly></td>
                ${taxEnabled() ? `<td><input class="form-control pr-calc" type="number" step="0.01" min="0" max="100" name="tax_percent" value="${esc(item.tax_percent || "0")}" readonly></td>` : `<input type="hidden" name="tax_percent" value="0">`}
                <td><input class="form-control pr-line-total" readonly value="${esc(item.line_total || "0.00")}"></td>
                <td class="text-end"><button class="btn btn-sm btn-outline-danger pr-remove-row" type="button">X</button></td>
            </tr>
        `;
    }

    function populatePurchases(select, purchases) {
        const current = select.value;
        select.innerHTML = `<option value="">Select</option>` + (purchases || []).map((purchase) => {
            const selected = String(purchase.id) === String(current) ? " selected" : "";
            return `<option value="${esc(purchase.id)}" data-supplier-id="${esc(purchase.supplier_id)}" data-bill-no="${esc(purchase.supplier_bill_no)}"${selected}>${esc(purchase.purchase_no)}</option>`;
        }).join("");
    }

    async function loadSupplierPurchases(form, supplierId) {
        const purchaseSelect = form.querySelector('[name="supplier_purchase_id"]');
        if (!purchaseSelect || !form.dataset.purchasesUrlTemplate) return;
        if (!supplierId) return;
        const response = await fetch(urlFromTemplate(form.dataset.purchasesUrlTemplate, supplierId), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch supplier purchases.");
        populatePurchases(purchaseSelect, payload.purchases || []);
    }

    async function loadPurchaseItems(form, purchaseId) {
        const tableBody = document.querySelector("#purchase-return-items tbody");
        if (!tableBody) return;
        tableBody.innerHTML = "";
        if (!purchaseId) {
            recalcAll();
            return;
        }
        const response = await fetch(urlFromTemplate(form.dataset.itemsUrlTemplate, purchaseId), {headers: {"X-Requested-With": "XMLHttpRequest"}});
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Unable to fetch purchase items.");
        const supplierSelect = form.querySelector('[name="supplier_id"]');
        if (supplierSelect && payload.supplier_id) supplierSelect.value = payload.supplier_id;
        const billInput = form.querySelector('[name="supplier_bill_no"]');
        if (billInput) billInput.value = payload.supplier_bill_no || "";
        tableBody.innerHTML = (payload.items || []).map(rowHtml).join("");
        recalcAll();
    }

    document.addEventListener("input", (event) => {
        if (event.target.classList.contains("pr-calc")) recalcAll();
    });

    document.addEventListener("click", (event) => {
        const button = event.target.closest(".pr-remove-row");
        if (!button) return;
        button.closest("tr")?.remove();
        recalcAll();
    });

    document.addEventListener("change", async (event) => {
        const form = event.target.closest("form");
        if (!form) return;
        try {
            if (event.target.name === "supplier_id") {
                await loadSupplierPurchases(form, event.target.value);
                document.querySelector("#purchase-return-items tbody").innerHTML = "";
                recalcAll();
            }
            if (event.target.name === "supplier_purchase_id") {
                await loadPurchaseItems(form, event.target.value);
            }
        } catch (error) {
            alert(error.message || "Unable to update purchase return items.");
        }
    });

    recalcAll();
})();
