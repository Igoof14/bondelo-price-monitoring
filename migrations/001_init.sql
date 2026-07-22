-- Инициализация схемы сервиса мониторинга цен.
-- Идемпотентно: можно запускать повторно.

-- Глобальная история цен облигаций с MOEX (в % от номинала).
CREATE TABLE IF NOT EXISTS moex_bond_prices (
    id          bigserial PRIMARY KEY,
    secid       text        NOT NULL,
    boardid     text        NOT NULL,
    price       numeric     NOT NULL,  -- % от номинала
    prev_close  numeric     NOT NULL,  -- закрытие предыдущей сессии (PREVPRICE)
    change_pct  numeric     NOT NULL,  -- (price - prev_close) / prev_close * 100
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mbp_secid_time
    ON moex_bond_prices (secid, recorded_at DESC);

-- Пересоздание price_alert_sent под новую схему (figi -> secid, без daily_count).
-- Старые данные транзитные (ретеншн 7 дней), потеря не критична.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'price_alert_sent' AND column_name = 'figi'
    ) THEN
        DROP TABLE price_alert_sent;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS price_alert_sent (
    id          bigserial   PRIMARY KEY,
    telegram_id bigint      NOT NULL,
    secid       text        NOT NULL,
    alert_type  varchar(32) NOT NULL,  -- drop_warning|drop_critical|rise_warning|rise_critical
    sent_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pas_user_secid_time
    ON price_alert_sent (telegram_id, secid, sent_at DESC);
