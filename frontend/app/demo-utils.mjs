export function activeVerificationCases(items) {
  return items.filter((item) => item.case?.status === "MUSTERI_DOGRULAMA");
}

export function unseenVerificationIds(items, seenIds) {
  return activeVerificationCases(items)
    .map((item) => item.case.id)
    .filter((id) => !seenIds.has(id));
}

export function highRiskQuickFill() {
  return {
    amount: "48500",
    transaction_type: "TRANSFER",
    recipient: "Demo Alıcı",
    source_device: "Yeni iPhone",
    city: "Berlin",
    occurred_at: "2026-07-23T01:30:00.000Z",
    transaction_frequency_24h: 20,
    is_new_device: true,
    home_city: "Istanbul",
  };
}

export function normalQuickFill() {
  return {
    amount: "250",
    transaction_type: "FATURA",
    recipient: "Elektrik Faturası",
    source_device: "Bilinen iPhone",
    city: "Istanbul",
    occurred_at: "2026-07-23T12:00:00.000Z",
    transaction_frequency_24h: 1,
    is_new_device: false,
    home_city: "Istanbul",
  };
}
