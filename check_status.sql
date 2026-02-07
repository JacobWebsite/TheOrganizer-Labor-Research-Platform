SELECT state, COUNT(*) as records, SUM(num_employees) as workers 
FROM manual_employers 
WHERE sector = 'PUBLIC' 
GROUP BY state 
ORDER BY SUM(num_employees) DESC;
