# Research Report: Cosine Similarity and Alternatives

**Project:** Occupation-Based Similarity + Workforce Estimation
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the second research task for the "Occupation-Based Similarity + Workforce Estimation" project was to investigate the use of cosine similarity for comparing occupation vectors. The key questions were:
1.  Are there published code examples or papers using this technique with BLS OEWS data?
2.  Are there alternative similarity measures that might be better for comparing proportions?

## 2. Summary of Findings

- **Cosine similarity is a standard and appropriate technique** for this use case. While no academic papers were found that apply it *specifically* to BLS OEWS data for comparing employer similarity, the method itself is a well-established data science technique for comparing the orientation of vectors. Code examples are readily available.
- **"Occupation vectors" must be constructed.** The BLS does not provide pre-built vectors. They must be created by selecting relevant features from the OEWS data (e.g., the proportion of total employment for each occupation code).
- **Theoretically superior alternatives exist, but they are more complex.** For a project with limited developer resources, starting with the simplest effective method is recommended.

## 3. Code Example for Cosine Similarity

Implementing cosine similarity in Python is straightforward using the `scikit-learn` library.

**Conceptual Workflow:**
1.  **Create Occupation Vectors:** For each employer (or industry), create a vector where each element is the proportion of the workforce in a specific occupation (SOC code).
2.  **Compute Similarity:** Use `sklearn.metrics.pairwise.cosine_similarity` to compute the similarity between these vectors.

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Example:
# Vector for a hospital (high % of nurses, low % of engineers)
hospital_vector = np.array([[0.30, 0.05, 0.01]]) # [nurses, aides, engineers]

# Vector for a software company (low % of nurses, high % of engineers)
software_co_vector = np.array([[0.01, 0.01, 0.45]])

# Vector for a nursing home (high % of nurses and aides)
nursing_home_vector = np.array([[0.25, 0.40, 0.00]])

# Compute similarity
similarity_score = cosine_similarity(hospital_vector, nursing_home_vector)
# Result will be a value between 0 and 1, where 1 is most similar.
print(f"Similarity between hospital and nursing home: {similarity_score[0][0]:.2f}")
```

## 4. Alternatives to Cosine Similarity

While cosine similarity is a good starting point, other metrics are designed specifically for compositional data (i.e., proportions that sum to 1).

| Alternative | Pros | Cons |
| :--- | :--- | :--- |
| **Aitchison Distance**| The most **theoretically correct** method for compositional data. | Requires a non-trivial "log-ratio transformation" of the data, adding complexity. |
| **Hellinger Distance**| Another strong choice for comparing probability distributions. | Less commonly used than cosine similarity. |
| **Euclidean Distance**| Simple and intuitive. | Sensitive to the magnitude of differences, not just the proportional mix. Less suitable for this specific problem. |

## 5. Recommendation

The project should **begin by implementing cosine similarity**. It is:
- **Effective:** It correctly measures the similarity of the *mix* of occupations, which is the core of the problem.
- **Simple to Implement:** The code is minimal and relies on standard libraries.
- **Well-Understood:** It's a common technique, making it easy to debug and explain.

If, after initial implementation and testing, it is determined that a more nuanced measure is required, **Aitchison Distance** should be the first alternative to be investigated. However, for the initial build, the simplicity and effectiveness of cosine similarity make it the clear choice.

This concludes the research on cosine similarity.
---
