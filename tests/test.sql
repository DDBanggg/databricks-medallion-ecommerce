SELECT 
    product_category_name,
    sum(total_revenue) as revenue
FROM olist_catalog.gold.daily_revenue
WHERE customer_state = 'SP'
GROUP BY product_category_name
ORDER BY revenue DESC
LIMIT 5;