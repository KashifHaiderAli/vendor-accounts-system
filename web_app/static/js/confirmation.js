(function () {
  const typeSelect = document.getElementById("confirmationType");
  const poNumber = document.getElementById("poNumber");
  const quotationSelect = document.getElementById("confirmationQuotation");
  const totalInput = document.getElementById("confirmationTotal");
  const contactInput = document.getElementById("confirmationContact");
  const customerSelect = document.getElementById("confirmationCustomer");

  function syncPoRequirement() {
    if (!typeSelect || !poNumber) return;
    const isPo = typeSelect.value === "PO";
    poNumber.required = isPo;
    const label = document.querySelector('label[for="poNumber"]');
    if (label) label.classList.toggle("required", isPo);
  }

  function syncQuotationDefaults() {
    if (!quotationSelect) return;
    const selected = quotationSelect.options[quotationSelect.selectedIndex];
    if (!selected || !selected.value) {
      if (customerSelect) customerSelect.disabled = false;
      return;
    }
    if (totalInput && selected.dataset.total && (!totalInput.value || Number(totalInput.value) === 0)) {
      totalInput.value = Number(selected.dataset.total || 0).toFixed(2);
    }
    if (contactInput && selected.dataset.contact && !contactInput.value) {
      contactInput.value = selected.dataset.contact;
    }
    if (customerSelect) customerSelect.disabled = false;
  }

  if (typeSelect) {
    typeSelect.addEventListener("change", syncPoRequirement);
    syncPoRequirement();
  }
  if (quotationSelect) {
    quotationSelect.addEventListener("change", syncQuotationDefaults);
    syncQuotationDefaults();
  }
})();
