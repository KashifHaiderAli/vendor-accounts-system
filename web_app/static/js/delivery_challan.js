document.addEventListener("DOMContentLoaded", () => {
    const body = document.querySelector("#deliveryItemsBody");
    const addButton = document.querySelector("#addDeliveryRow");
    const template = document.querySelector("#deliveryRowTemplate");
    if (!body || !template) return;

    const bindRow = (row) => {
        row.querySelector(".remove-row")?.addEventListener("click", () => {
            if (body.querySelectorAll(".delivery-item-row").length > 1) {
                row.remove();
            }
        });
        row.querySelector(".item-select")?.addEventListener("change", (event) => {
            const option = event.target.selectedOptions[0];
            const description = row.querySelector("[name='description[]']");
            if (option?.dataset.description && description && !description.value.trim()) {
                description.value = option.dataset.description;
            }
        });
    };

    addButton?.addEventListener("click", () => {
        const clone = template.content.firstElementChild.cloneNode(true);
        body.appendChild(clone);
        bindRow(clone);
    });

    body.querySelectorAll(".delivery-item-row").forEach(bindRow);
});
