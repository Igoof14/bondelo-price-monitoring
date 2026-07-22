-- ВНИМАНИЕ: запускать ВРУЧНУЮ и только ПОСЛЕ отключения старого
-- scheduler-джоба мониторинга цен в монорепе бота — он всё ещё пишет
-- в эти таблицы.
--
-- scripts/migrate.py этот файл НЕ применяет.

DROP TABLE IF EXISTS bond_price_history;
DROP TABLE IF EXISTS bond_last_price;
