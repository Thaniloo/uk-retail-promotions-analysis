-- 04_campaign_did.sql : inputs for the difference-in-differences promotion lift
-- For each campaign: the campaign window and an equal-length window just before it,
-- and average weekly spend per household in each window, for targeted vs not targeted.
-- Only campaigns whose pre-window sits fully inside the data (2017) are used.

-- name: campaign_windows
SELECT campaign_id,
       campaign_type,
       start_date,
       MIN(end_date, '2017-12-31') AS end_date,
       DATE(start_date, '-' || CAST(JULIANDAY(MIN(end_date, '2017-12-31')) - JULIANDAY(start_date) + 1 AS INT) || ' days') AS pre_start,
       DATE(start_date, '-1 day') AS pre_end,
       CAST(JULIANDAY(MIN(end_date, '2017-12-31')) - JULIANDAY(start_date) + 1 AS INT) AS window_days,
       (SELECT COUNT(*) FROM campaigns c WHERE c.campaign_id = d.campaign_id) AS targeted_households
FROM campaign_descriptions d
WHERE DATE(start_date, '-' || CAST(JULIANDAY(MIN(end_date, '2017-12-31')) - JULIANDAY(start_date) + 1 AS INT) || ' days') >= '2017-01-01';

-- name: household_window_spend
-- One row per campaign x household x window, for households active in both halves of the year.
WITH win AS (
    SELECT campaign_id, campaign_type, start_date,
           MIN(end_date, '2017-12-31') AS end_date,
           CAST(JULIANDAY(MIN(end_date, '2017-12-31')) - JULIANDAY(start_date) + 1 AS INT) AS days
    FROM campaign_descriptions
),
win2 AS (
    SELECT *, DATE(start_date, '-' || days || ' days') AS pre_start FROM win
    WHERE DATE(start_date, '-' || days || ' days') >= '2017-01-01'
),
active AS (       -- the comparison pool: households that shop all year
    SELECT household_id FROM transactions
    GROUP BY household_id
    HAVING COUNT(DISTINCT basket_id) >= 10
       AND MIN(DATE(transaction_timestamp)) <= '2017-02-28'
       AND MAX(DATE(transaction_timestamp)) >= '2017-11-01'
),
daily AS (
    SELECT household_id, DATE(transaction_timestamp) AS d, SUM(sales_value) AS spend
    FROM transactions GROUP BY household_id, d
)
SELECT w.campaign_id, w.campaign_type, a.household_id,
       CASE WHEN c.household_id IS NOT NULL THEN 1 ELSE 0 END AS targeted,
       w.days,
       COALESCE(SUM(CASE WHEN dl.d BETWEEN w.pre_start AND DATE(w.start_date, '-1 day') THEN dl.spend END), 0) * 7.0 / w.days AS pre_weekly_spend,
       COALESCE(SUM(CASE WHEN dl.d BETWEEN w.start_date AND w.end_date THEN dl.spend END), 0) * 7.0 / w.days AS during_weekly_spend
FROM win2 w
CROSS JOIN active a
LEFT JOIN campaigns c ON c.campaign_id = w.campaign_id AND c.household_id = a.household_id
LEFT JOIN daily dl ON dl.household_id = a.household_id AND dl.d BETWEEN w.pre_start AND w.end_date
GROUP BY w.campaign_id, w.campaign_type, a.household_id;

-- name: household_strata
-- Shopping-intensity deciles. Targeted households shop about twice as much as the rest,
-- so lift is compared within deciles (like with like), then averaged.
SELECT household_id, NTILE(10) OVER (ORDER BY COUNT(DISTINCT basket_id)) AS intensity_decile
FROM transactions GROUP BY household_id;
