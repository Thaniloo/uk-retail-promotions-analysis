-- 03_rfm.sql : recency / frequency / monetary scores per household
-- Households with fewer than 5 baskets in the year are excluded (see 01_profile.sql).

-- name: rfm
WITH hh AS (
    SELECT household_id,
           JULIANDAY('2017-12-31') - JULIANDAY(MAX(DATE(transaction_timestamp))) AS recency_days,
           COUNT(DISTINCT basket_id)  AS frequency,
           SUM(sales_value)           AS monetary
    FROM transactions
    WHERE DATE(transaction_timestamp) <= '2017-12-31'
    GROUP BY household_id
    HAVING COUNT(DISTINCT basket_id) >= 5
),
scored AS (
    SELECT *,
           6 - NTILE(5) OVER (ORDER BY recency_days) AS r_score,   -- 5 = most recent
           NTILE(5) OVER (ORDER BY frequency)        AS f_score,   -- 5 = most frequent
           NTILE(5) OVER (ORDER BY monetary)         AS m_score    -- 5 = highest spend
    FROM hh
)
SELECT household_id, recency_days, frequency, ROUND(monetary, 2) AS monetary,
       r_score, f_score, m_score,
       CASE
         WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
         WHEN r_score >= 3 AND f_score >= 3                  THEN 'Loyal regulars'
         WHEN r_score >= 4 AND f_score <= 2                  THEN 'New or occasional'
         WHEN r_score <= 2 AND f_score >= 3                  THEN 'At risk'
         WHEN r_score <= 2 AND f_score <= 2                  THEN 'Lapsed'
         ELSE 'Middle of the road'
       END AS segment
FROM scored;
