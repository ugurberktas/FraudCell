function numericStatus(error) {
  const status = Number(error?.status);
  return Number.isFinite(status) ? status : 0;
}

function errorCode(error) {
  return typeof error?.code === "string" ? error.code : "";
}

function errorMessage(error, fallback) {
  return typeof error?.message === "string" && error.message.trim()
    ? error.message.trim()
    : fallback;
}

export function apiErrorText(error, fallback = "İşlem tamamlanamadı") {
  const status = numericStatus(error);
  const message = errorMessage(error, fallback);

  if (status === 0 || status >= 500 || errorCode(error) === "SERVICE_UNAVAILABLE") {
    return `Servise şu anda ulaşılamıyor. ${message}`;
  }
  if (status === 401) return `Oturum doğrulanamadı (401). ${message}`;
  if (status === 403) return `Bu işlem için yetkiniz yok (403). ${message}`;
  if (status === 422) return `İşlem mevcut durumda uygulanamaz (422). ${message}`;
  if (status === 429) return `Çok fazla istek gönderildi (429). ${message}`;
  return message;
}

export function loginErrorText(error) {
  const status = numericStatus(error);
  const code = errorCode(error);

  if (code === "ACCOUNT_LOCKED") {
    const rawSeconds = Number(error?.details?.remaining_seconds);
    const suffix = Number.isFinite(rawSeconds) && rawSeconds > 0
      ? ` Yaklaşık ${Math.ceil(rawSeconds)} saniye sonra tekrar deneyin.`
      : " Daha sonra tekrar deneyin.";
    return `Hesap çok sayıda başarısız giriş nedeniyle kilitlendi (429).${suffix}`;
  }
  if (status === 429) {
    return "Çok fazla giriş denemesi yapıldı (429). Lütfen daha sonra tekrar deneyin.";
  }
  if (status === 401) {
    return "Giriş bilgileri doğrulanamadı (401). GSM/OTP veya e-posta/parolayı kontrol edin.";
  }
  if (status === 0 || status >= 500 || code === "SERVICE_UNAVAILABLE") {
    return "Kimlik servisine şu anda ulaşılamıyor. Platform durumunu kontrol edip tekrar deneyin.";
  }
  return apiErrorText(error, "Giriş tamamlanamadı");
}

export function remainingSlaSeconds(dueAt, nowMs = Date.now()) {
  const dueMs = Date.parse(dueAt);
  if (!Number.isFinite(dueMs)) return null;
  return Math.max(0, Math.ceil((dueMs - nowMs) / 1000));
}

export function newlyEarnedBadges(previous, current) {
  const known = new Set(previous || []);
  return (current || []).filter((badge) => !known.has(badge));
}

export function summarizeCases(cases) {
  const activeStatuses = new Set(["YENI", "ATANDI", "INCELENIYOR", "MUSTERI_DOGRULAMA"]);
  return (cases || []).reduce(
    (summary, item) => {
      if (activeStatuses.has(item.status)) summary.active += 1;
      if (activeStatuses.has(item.status) && item.transaction?.risk_level === "KRITIK") summary.critical += 1;
      if (item.sla_exceeded) summary.slaExceeded += 1;
      if (item.status === "YENI" && !item.assigned_analyst_id) summary.queued += 1;
      return summary;
    },
    { active: 0, critical: 0, slaExceeded: 0, queued: 0 },
  );
}

export function countBy(values) {
  const counts = new Map();
  for (const value of values || []) {
    const label = typeof value === "string" && value.trim() ? value : "Bilinmiyor";
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

export function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    String(value || "").trim(),
  );
}
