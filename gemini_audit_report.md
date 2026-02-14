# Gemini Blind Audit Report: Labor Relations Research Platform

**Date:** February 14, 2026
**Auditor:** Gemini

## 1. Introduction and Executive Summary

This document presents an independent, "blind" audit of the Labor Relations Research Platform. The audit was conducted with a fresh perspective, without prior knowledge of the system's architecture or development history, which was primarily driven by another AI assistant (Claude).

The platform is a powerful and ambitious project that aims to consolidate and analyze a vast amount of labor-related data to support union organizing efforts. My audit confirms that the project has achieved significant successes, particularly in the complex areas of union membership deduplication and public sector reconciliation. The existing documentation is thorough, and the data schema is well-designed.

However, the project is at a critical inflection point, moving from a data-centric research tool to a production-ready, multi-user application. This audit focuses on the key areas that need to be addressed to make this transition successful, as outlined in the project's own comprehensive roadmap (`LABOR_PLATFORM_ROADMAP_v13.md`).

**Key Findings:**

*   **Strengths:**
    *   **Successful Data Reconciliation:** The platform's ability to reconcile disparate data sources to produce accurate union membership numbers is a major achievement.
    *   **Robust Database:** The PostgreSQL database is well-designed, with a clear schema, extensive use of views for data aggregation, and good indexing.
    *   **Comprehensive Testing:** The API has a surprisingly robust suite of integration tests.
    *   **Advanced Matching:** The core matching pipeline is a sophisticated piece of software.

*   **Areas for Improvement:**
    *   **Data Matching Rates:** The low match rates between key datasets (OSHA, WHD, IRS 990) and the core employer table is the most critical issue limiting the platform's analytical power.
    *   **Frontend Monolith:** The single-file, 10,000+ line HTML frontend is a major source of technical debt and will be difficult to maintain or extend.
    *   **API Producion-Readiness:** While the API is more modular than the roadmap suggests, it still has security and scalability issues that need to be addressed before deployment.
    *   **Script Orchestration:** The large number of ETL and data processing scripts lack a clear orchestration system, making the data pipeline brittle and hard to manage.

This report will provide a detailed analysis of these areas, as well as prioritized recommendations for improvement.

---
## 2. Data: Match Rate Improvements

**Status:** Significant progress has been made, but further improvement is possible.

### Summary
The ability to link disparate datasets to a central employer record is the single most important factor for the platform's analytical power. The LABOR_PLATFORM_ROADMAP_v13.md correctly identifies low match rates as the most critical gap in the platform.

### Findings
My audit confirms that this has been an area of active development. The match rates I calculated are significantly higher than those reported in the roadmap from February 10, 2026:

| Data Source | Current Match Rate (Feb 14) | Roadmap Match Rate (Feb 10) | Improvement |
|---|---|---|---|
| OSHA | 13.73% | 7.9% | +74% |
| WHD | 6.77% | 4.8% | +41% |
| IRS 990 National | 2.40% | 0.0% | +8 |

This is a fantastic improvement in a very short amount of time and should be celebrated. The work done on matching since the roadmap was written has clearly been effective.

However, while the rates have improved, there is still room for growth. A 14% match rate for OSHA, for example, still means that 86% of OSHA establishments are not being fully leveraged in the platform's analysis.

### Analysis of Roadmap
The roadmap outlines a clear, multi-tiered strategy for improving match rates (Checkpoint 5.1, 5.2, 5.3). These strategies, including corporate parent matching, address-first matching, and aggressive name normalization, are all sound and are likely responsible for the improvements I've observed.

The roadmap's proposed strategies are still highly relevant and should be continued. The 4-tier matching strategy outlined in the roadmap is a solid foundation.

### Recommendations
1.  **Continue with the Roadmap:** The matching strategies outlined in the roadmap are excellent. I recommend continuing with the plans for corporate parent matching, address-based matching, and NAICS-constrained fuzzy matching.
2.  **Focus on splink:** The scripts/matching directory contains scripts for splink, a powerful probabilistic matching library. The roadmap mentions splink but doesn't make it a central part of the matching improvement plan. I recommend elevating the use of splink for all matching scenarios. It is more powerful and flexible than the current tiered approach and can handle more complex matching scenarios. A well-configured splink model can often outperform a series of hand-tuned heuristic tiers.
3.  **Human-in-the-loop:** For the most important data sources (like OSHA and WHD), I recommend implementing a human-in-the-loop system for reviewing borderline matches. This could be a simple web interface where a user can confirm or deny matches that the model is uncertain about. This would improve match quality and provide valuable training data for the matching models. The roadmap mentions this, and I want to strongly endorse it.
4.  **Prioritize OSHA:** The OSHA dataset is a goldmine of information for organizing. A high match rate here is critical. I recommend focusing engineering effort on getting the OSHA match rate above 25%.
5.  **Update the Roadmap:** The roadmap should be updated to reflect the new baseline match rates. This will provide a more accurate picture of the project's current state and help prioritize future work.

---
## 3. Data: New Sources

**Status:** The roadmap provides an excellent list of high-value data sources to pursue.

### Summary
The platform's value is directly proportional to the breadth and quality of its data. The roadmap identifies seven new data sources to enrich the platform's analytical capabilities.

### Analysis of Roadmap
The new data sources proposed in the roadmap (Checkpoint 6.1 to 6.7) are all excellent choices. I will briefly assess each one:

*   **FMCS Contract Expiration Data (Checkpoint 6.1):** **Highest Priority.** This is the single most valuable addition proposed. Contract expirations are a critical trigger for organizing campaigns. The roadmap's plan to add this data and a score_contract_timing to the scorecard is exactly right.
*   **NLRB Real-Time Case Monitoring (Checkpoint 6.2):** **High Priority.** Real-time awareness of new petitions and ULP charges is highly actionable intelligence. The proposed daily monitoring script is a great idea.
*   **FEC Political Contribution Data (Checkpoint 6.3):** **Medium Priority.** This is a great source for "vulnerability" research. Knowing an employer's political spending can be powerful in a campaign.
*   **DOL Enforcement Data (Checkpoint 6.4):** **Medium Priority.** Expanding beyond WHD to other DOL agencies like MSHA and OFCCP is a good way to get more violation data.
*   **Census County Business Patterns (Checkpoint 6.5):** **Medium Priority.** This data provides the "denominator" for market penetration analysis, which is a valuable strategic tool.
*   **Mergent National Expansion (Checkpoint 6.6):** **High Priority.** Mergent is a rich source of corporate data. Expanding it nationally is crucial for the platform's success. The manual extraction process is a bottleneck, but the value is worth the effort.
*   **State PERB Data (Checkpoint 6.7):** **Medium Priority.** This is important for strengthening the public sector data, which is currently a weak point.

### Recommendations
The roadmap's plan for new data sources is comprehensive and well-thought-out. My recommendations are focused on prioritization and alternative acquisition strategies.

1.  **Prioritize FMCS and NLRB:** The FMCS and NLRB real-time data are the most actionable for organizers. These should be the top priorities.
2.  **Automate Mergent Extraction:** The manual extraction of Mergent data is a significant bottleneck. I recommend exploring ways to automate this. While direct web scraping of library portals is often difficult and against their terms of service, it might be possible to use a tool like [Crawl4AI](https://github.com/leviolson/Crawl4AI) to build a semi-automated extraction process that is more robust than pure manual clicking.
3.  **Alternative to FEC Data:** Instead of directly processing FEC data, consider using the OpenSecrets.org API. They provide pre-processed, cleaned, and well-structured data on political contributions and lobbying, which can save a significant amount of development time. They have a free tier that should be sufficient for initial development.
4.  **Consider State and Local Government Contract Data:** The roadmap includes federal contract data from USAspending.gov. I recommend expanding this to include state and local government contract data. Many states and large cities have open data portals that publish this information. This would be particularly valuable for public sector organizing.
5.  **News and Media Monitoring:** The roadmap mentions this as a "Post-Launch Growth" item (Checkpoint 12.7), but I recommend moving it up in priority. Real-time news alerts about strikes, layoffs, or other labor-related events can be highly valuable. Instead of building a custom solution, consider using a news API service like [NewsAPI.org](https://newsapi.org/) or [GNews.io](https://gnews.io/).

---
## 4. API: Restructure & Harden

**Status:** Good progress has been made, but critical security and scalability issues remain.

### Summary
The API is the backbone of the platform, serving data to the frontend and potentially to external clients. The roadmap correctly identifies several critical areas for improvement to make the API production-ready.

### Findings
My audit of the pi/ directory reveals that the API is in a better state than the roadmap suggests. The main.py file shows that the API has already been partially decomposed into separate router files, and middleware for authentication, rate limiting, and logging is already in place.

However, the roadmap's core concerns are still valid:
*   **Authentication is disabled by default.** The AuthMiddleware is a no-op unless a LABOR_JWT_SECRET is set. This is a major security risk.
*   **CORS is wide open.** llow_origins=["*"] allows any website to make requests to the API, which is a security vulnerability.
*   **No Pagination on many endpoints.** The roadmap correctly identifies that many endpoints can return a huge number of records, which can lead to performance issues and denial-of-service vulnerabilities.
*   **In-memory Rate Limiting.** The rate limiter will not work correctly in a multi-instance deployment.

### Analysis of Roadmap
The roadmap's plan for the API (Checkpoint 7.1 to 7.5) is excellent and comprehensive. It addresses all of the key issues I've identified.

*   **Module Decomposition (7.1):** This is already partially done, which is great. The plan to complete this is the right approach.
*   **Pagination & Input Validation (7.2):** This is a critical step for performance and security. The use of Pydantic for input validation is a best practice.
*   **Authentication & Authorization (7.3):** The plan to implement JWT-based authentication with roles is the right one. The foundation for this is already in the code, it just needs to be enabled and enforced.
*   **Error Handling & Logging (7.4):** The existing logging middleware is a good start. The plan to implement global error handling and consistent error responses is excellent.
*   **API Versioning (7.5):** Versioning the API (/api/v1/) is a crucial step for long-term maintainability.

### Recommendations
My recommendations for the API are largely in line with the roadmap, with a few additional suggestions.

1.  **Enable Authentication Immediately:** The first step should be to enable the existing authentication middleware by setting a LABOR_JWT_SECRET in the .env file. All subsequent development should be done with authentication enabled.
2.  **Lock Down CORS:** The llow_origins setting in the CORSMiddleware should be changed from ["*"] to a specific list of allowed domains (e.g., the domain where the frontend is hosted).
3.  **Prioritize Pagination:** The lack of pagination is a serious performance and security risk. I recommend prioritizing the implementation of limit/offset pagination on all list endpoints.
4.  **Use a Production-Ready Rate Limiter:** For a production deployment, the in-memory rate limiter should be replaced with a more robust solution that uses a shared store like Redis. There are several good libraries for this, such as slowapi.
5.  **SQL Injection Risk:** The roadmap mentions "SQL via f-strings". While it notes the current pattern is safe-but-fragile, I want to strongly recommend moving to a proper query-building library like SQLAlchemy Core. This will provide better security, type safety, and maintainability. Using an ORM like SQLAlchemy ORM might be too heavy for this project, but the expression language of SQLAlchemy Core is a perfect fit. This will eliminate the risk of SQL injection entirely.
6.  **Asynchronous Database Access:** The current database connection is synchronous (psycopg2). To take full advantage of FastAPI's asynchronous capabilities, I recommend switching to an async database driver like syncpg and using a library like databases or SQLAlchemy's async support. This will improve the API's performance and scalability.

---
## 5. Frontend: Production Polish

**Status:** The frontend is a major source of technical debt and requires a significant refactoring effort.

### Summary
The frontend is the face of the platform, and its usability and performance are critical to the project's success. The current frontend is a single, massive HTML file with over 10,000 lines of inline JavaScript and CSS. This is a classic "monolithic frontend" and is not sustainable for a production application.

### Findings
My audit of iles/organizer_v5.html confirms the roadmap's assessment. The frontend is:
*   **A Single File:** All HTML, CSS, and JavaScript are in one file.
*   **Lacking a Build Step:** There is no modern frontend build process, which means no code splitting, minification, or modern JavaScript features.
*   **Imperative and State-heavy:** The JavaScript code uses a lot of direct DOM manipulation and manages a complex state in global variables.
*   **Not Responsive:** The UI is not designed for mobile devices.
*   **Accessibility Issues:** The roadmap identifies several accessibility issues.

### Analysis of Roadmap
The roadmap's plan for the frontend (Checkpoint 8.1 to 8.5) is excellent. It correctly identifies the key areas that need to be addressed.

*   **Code Architecture Refactor (8.1):** The plan to extract the CSS and JavaScript into separate files and use ES6 modules is the right first step. This will immediately improve the organization and maintainability of the code.
*   **Accessibility (8.2):** The roadmap provides a good list of accessibility improvements to target WCAG 2.1 AA compliance.
*   **Mobile Responsiveness (8.3):** The plan to add responsive breakpoints and make the UI usable on mobile devices is crucial.
*   **Error Recovery & Loading States (8.4):** Improving the user experience around errors and loading is important for a production application.
*   **UX Improvements (8.5):** The proposed UX improvements, like URL routing and keyboard shortcuts, will make the application much more pleasant to use.

### Recommendations
The roadmap provides a solid plan for refactoring the existing frontend. However, I want to propose a more aggressive, long-term solution.

1.  **Adopt a Modern Frontend Framework:** Instead of just refactoring the existing JavaScript, I strongly recommend migrating the frontend to a modern framework like **React**, **Vue**, or **Svelte**. My recommendation would be **React** with a build tool like **Vite**.
    *   **Why?** A framework like React will provide a much better structure for the application, with a component-based architecture, declarative rendering, and a robust ecosystem of libraries. This will make the frontend much easier to maintain, test, and extend in the long run.
    *   **Migration Path:** This doesn't have to be a "big bang" rewrite. The team could start by building new features in React and gradually migrating existing features over time. The "Strangler Fig" pattern is a good approach for this.
2.  **Use a Component Library:** To accelerate development and ensure a consistent UI, I recommend using a component library like **Material-UI (MUI)** or **Ant Design**. These libraries provide a set of pre-built, accessible, and themeable components that can be used to build the UI much faster.
3.  **Implement a State Management Solution:** For a complex application like this, a dedicated state management library is essential. For React, I recommend **Redux Toolkit** or **Zustand**. This will provide a single source of truth for the application's state and make it much easier to manage.
4.  **Prioritize the "Minimum Viable Refactor":** If a full framework migration is not feasible right now, the team should focus on the "minimum viable refactor" outlined in the roadmap: extracting CSS and JS into separate files. This will at least make the code more manageable.
5.  **Focus on the Core User Journey:** The current UI is very complex, with many modals and different modes. As part of the redesign/refactor, I recommend focusing on the core user journey of an organizer: **"Find a target, research it, and take action."** The UI should be streamlined to support this workflow as efficiently as possible.

---
## 6. DevOps: Deployment

**Status:** The project is not yet deployed, but the roadmap provides a solid plan for doing so.

### Summary
A powerful platform is only useful if it's accessible to its users. The project is currently a local-only application. The roadmap outlines a comprehensive plan for deploying the platform to the cloud.

### Findings
My audit confirms that the project is not yet set up for deployment. There are no Dockerfiles, no CI/CD pipelines, and no cloud infrastructure. The project runs locally, and that's it.

### Analysis of Roadmap
The roadmap's deployment plan (Checkpoint 9.1 to 9.6) is excellent. It covers all the essential steps for a production deployment.

*   **Containerization (9.1):** The plan to use Docker and docker-compose is the right approach. This will ensure a consistent and reproducible environment for the application.
*   **Cloud Hosting (9.2):** The cost comparison of different cloud providers is very helpful. The recommendation to start with a simple PaaS like Render or Railway is a good one.
*   **CI/CD Pipeline (9.3):** The plan to use GitHub Actions for CI/CD is a standard and effective choice. The proposed pipeline (test on push, deploy on merge to main) is a good starting point.
*   **Domain, SSL & DNS (9.4):** These are all essential steps for a production deployment.
*   **Monitoring & Alerting (9.5):** The plan to use tools like UptimeRobot and Sentry for monitoring is a good, low-cost way to get started.
*   **Data Pipeline Automation (9.6):** The plan to use a simple cron-based orchestrator for the ETL scripts is a pragmatic choice. A full-blown orchestration tool like Airflow would be overkill at this stage.

### Recommendations
The roadmap's deployment plan is very thorough. My recommendations are focused on a few key areas to ensure a smooth and secure deployment.

1.  **Infrastructure as Code (IaC):** While the roadmap's manual setup process is fine for an initial deployment, I recommend moving to an Infrastructure as Code (IaC) tool like **Terraform** or **Pulumi** in the long run. This will allow the team to manage the cloud infrastructure in a declarative and version-controlled way, which is much more robust and scalable.
2.  **Secret Management:** The current plan is to use a .env file for secrets. This is fine for local development, but for a production deployment, a more secure solution is needed. I recommend using a secret management service like **AWS Secrets Manager**, **Google Secret Manager**, or **HashiCorp Vault**. These services provide a secure and auditable way to store and access secrets.
3.  **Database Migration Strategy:** The roadmap mentions pg_dump for the initial database migration. This is fine, but for ongoing schema changes, a proper database migration tool is needed. I recommend using a tool like **Alembic** (for SQLAlchemy) or **flyway**. This will allow the team to manage database schema changes in a version-controlled and repeatable way.
4.  **Staging Environment:** The roadmap's CI/CD plan focuses on a main branch that deploys to production. I strongly recommend adding a develop or staging branch that deploys to a separate staging environment. This will allow the team to test changes in a production-like environment before deploying them to production. This is crucial for preventing bugs and downtime.
5.  **Log Aggregation:** The current plan is to use the hosting provider's log viewer. This is a good start, but for easier debugging and analysis, I recommend aggregating the logs from all services into a centralized logging platform like **Datadog**, **Logz.io**, or the **ELK stack (Elasticsearch, Logstash, Kibana)**.

---
## 7. Analytics: Predictive Model

**Status:** The current scoring model is a good heuristic, but the plan to move to a data-driven predictive model is the right long-term direction.

### Summary
The platform's core value proposition is its ability to identify and prioritize organizing targets. The current "Organizing Scorecard" is a heuristic model based on a set of hand-picked factors and weights. The roadmap outlines a plan to replace this with a data-driven predictive model.

### Findings
My audit of the code (scripts/scoring/) and documentation confirms that the current scorecard is a weighted sum of several factors, including OSHA violations, industry density, and company size. The weights for these factors appear to be hand-tuned. This is a reasonable approach for a first version, but it's not as powerful or accurate as a machine learning model.

### Analysis of Roadmap
The roadmap's plan for building a predictive model (Checkpoint 10.1 to 10.3) is excellent. It follows a standard and sound data science methodology.

*   **Historical Outcome Validation (10.1):** This is the most important step. Before building a new model, it's crucial to test whether the current scorecard has any predictive power. The plan to do this using historical NLRB election data is exactly right.
*   **Propensity Score Model (10.2):** The plan to build a logistic regression model to predict the probability of a workplace being unionized is a good starting point. The choice of features is reasonable, and the plan to use a holdout test set is a good practice.
*   **Composite Opportunity Score (10.3):** The idea of creating a composite score that combines similarity, vulnerability, and feasibility is a good one. This is a more nuanced approach than a simple propensity score.

### Recommendations
The roadmap provides a solid plan for developing a predictive model. My recommendations are focused on model selection, feature engineering, and MLOps.

1.  **Try More Powerful Models:** While logistic regression is a good starting point, I recommend exploring more powerful models like **Gradient Boosting (using libraries like XGBoost, LightGBM, or CatBoost)**. These models often provide better performance and can capture more complex, non-linear relationships in the data.
2.  **Feature Engineering is Key:** The performance of the model will depend heavily on the quality of the features. I recommend investing significant time in feature engineering. Some ideas for new features include:
    *   **Text-based features:** As mentioned in the roadmap (Checkpoint 12.4), using NLP to extract features from company descriptions, job postings, and news articles can be very powerful.
    *   **Network features:** The corporate hierarchy data can be used to create features like "number of unionized siblings" or "distance to the nearest unionized employer in the corporate tree."
    *   **Geospatial features:** The platform has a lot of geographic data. This can be used to create features like "density of union members in a 10-mile radius" or "distance to the nearest union hall."
3.  **MLOps:** As the team starts to build and deploy models, it will be important to adopt good MLOps (Machine Learning Operations) practices. This includes:
    *   **Experiment Tracking:** Using a tool like **MLflow** or **Weights & Biases** to track experiments, including code, data, parameters, and metrics. This is crucial for reproducibility.
    *   **Model Registry:** A central place to store and version trained models.
    *   **Model Monitoring:** Monitoring the performance of the deployed model over time to detect drift or degradation.
4.  **Explainability:** For a model that is being used to make important strategic decisions, explainability is crucial. I recommend using a library like **SHAP** to explain the model's predictions. This will help organizers understand *why* a particular workplace is being recommended as a target.

---
## 8. Code Quality and Maintainability

**Status:** The code quality is mixed, with a clear distinction between the well-structured backend and the monolithic frontend.

### Backend (Python)
The Python code in the pi/, scripts/matching/, and 	ests/ directories is generally of good quality.
*   **Strengths:**
    *   The code is well-formatted and follows PEP 8 conventions.
    *   The use of modern Python features (like type hints in some places) is good.
    *   The code is reasonably well-documented with docstrings.
    *   The API's modular structure is a big plus.
*   **Weaknesses:**
    *   The scripts/etl/ directory is a major pain point. It's a sprawling collection of over 60 scripts with no clear organization or orchestration. This makes the data pipeline very difficult to understand and maintain.
    *   The use of f-strings for building SQL queries, while currently safe, is a code smell and a potential security risk.

### Frontend (HTML/JS)
The frontend is the weakest part of the codebase. It's a single, 10,000+ line HTML file with inline JavaScript and CSS. This is a classic "spaghetti code" monolith and is a major source of technical debt. It will be very difficult to maintain, extend, or onboard new developers to this part of the codebase.

### Recommendations
1.  **Refactor the scripts/etl/ directory:** This is a high-priority task. The scripts should be reorganized into a clear, modular structure. A simple orchestration script (as proposed in the roadmap) should be created to define the data pipeline as code.
2.  **Eliminate f-string SQL:** All f-string-based SQL queries should be refactored to use a library like SQLAlchemy Core. This will improve security and maintainability.
3.  **Rewrite the Frontend:** As recommended in the "Frontend" section, the frontend should be rewritten using a modern framework.

## 9. Testing

**Status:** The project has a surprisingly good testing suite for its API, but no testing for the data pipelines or frontend.

### Findings
The 	ests/test_api.py file is a high-quality integration test suite that covers over 20 API endpoints. It tests for success cases, error cases, and even performance. This is a major strength of the project.

However, there are no tests for:
*   **ETL scripts:** The complex data processing logic in the scripts/etl/ directory is completely untested.
*   **Matching pipeline:** The core matching logic is not unit-tested.
*   **Frontend:** The JavaScript code in the frontend is not tested.

### Recommendations
1.  **Unit Test the Matching Pipeline:** The matching logic is a critical part of the system and should have comprehensive unit tests. Each of the matchers (EINMatcher, NormalizedMatcher, etc.) should be tested in isolation.
2.  **Add Data Validation Tests:** The ETL pipeline should have data validation tests that run at each stage to ensure the data is clean and consistent. A library like Great Expectations would be a good choice for this.
3.  **Implement Frontend Testing:** Once the frontend is refactored into a modern framework, unit and integration tests should be added using a library like Jest and React Testing Library.

## 10. Documentation

**Status:** The project has excellent high-level documentation, but the code-level documentation is inconsistent.

### Findings
The project's high-level documentation (CLAUDE.md, GEMINI.md, LABOR_PLATFORM_ROADMAP_v13.md, docs/METHODOLOGY_SUMMARY_v8.md) is excellent. It's clear, comprehensive, and provides a great overview of the project's goals, architecture, and methodology.

The code-level documentation is more mixed.
*   **Good:** The SQL schema is well-commented, and the API has some docstrings.
*   **Needs Improvement:** The scripts/etl/ directory is poorly documented. It's very difficult to understand what each script does without reading the code.

### Recommendations
1.  **Document the ETL Scripts:** Each script in the scripts/etl/ directory should have a clear docstring that explains its purpose, inputs, and outputs.
2.  **Generate an ERD:** The roadmap mentions creating a database ERD (Entity-Relationship Diagram). I strongly endorse this. A visual representation of the database schema would be very helpful.
3.  **Keep the Roadmap Updated:** The LABOR_PLATFORM_ROADMAP_v13.md is an excellent document, but it's already out of date in some areas (like the match rates). It should be treated as a living document and kept up-to-date.

## 11. Union Usability

**Status:** The platform is a powerful research tool, but it's not yet optimized for the fast-paced workflow of a union organizer.

### Organizer's Perspective
From the perspective of a union organizer, the platform provides a wealth of valuable data. The ability to search for employers, see their violation history, and identify potential organizing targets is a game-changer.

However, the current UI is complex and data-dense. An organizer in the field needs quick, actionable intelligence, not a complex research dashboard.

### Recommendations
1.  **"Target of the Week" Dashboard:** The main landing page for an organizer should be a simple dashboard that answers the question: "What are the top 5 organizing targets in my territory right now?" This should be a simple, actionable list, not a complex set of filters.
2.  **Mobile-First Design:** Organizers are often in the field, not at a desk. The frontend should be redesigned with a mobile-first approach, ensuring that the most important information is easily accessible on a phone.
3.  **Alerts and Notifications:** Organizers need to know about events as they happen. The platform should have a system for sending real-time alerts for things like:
    *   A new NLRB petition filed in their territory.
    *   A major safety violation at a key employer.
    *   A contract expiration at a target company.
4.  **Integration with Field Notes:** Organizers need a place to keep notes on their targets. The platform should have a simple note-taking feature that allows organizers to record their observations and track their progress.
5.  **Focus on "Why":** For each organizing target, the platform should provide a clear, concise summary of *why* it's a good target. For example: "This employer has a history of safety violations, its contract is expiring in 6 months, and it's in a high-density union area." This is more valuable than a simple numerical score.
## 12. Prioritized Improvements

This section provides a prioritized list of recommendations to guide the next phase of the project's development.

### Tier 1: Immediate Priorities (Next 1-2 Sprints)

These items address the most critical security, performance, and usability issues.

1.  **Enable API Authentication:** Immediately enable the existing JWT authentication middleware by setting the LABOR_JWT_SECRET in the .env file. This is a critical security fix.
2.  **Lock Down CORS:** Change the llow_origins setting in the CORSMiddleware to a specific list of allowed domains.
3.  **Implement API Pagination:** Add limit/offset pagination to all list-based API endpoints to prevent performance and security issues.
4.  **Frontend "Minimum Viable Refactor":** Extract the CSS and JavaScript from organizer_v5.html into separate files. This will immediately improve the maintainability of the frontend.
5.  **Update the Roadmap:** Update the LABOR_PLATFORM_ROADMAP_v13.md with the new, higher match rates to provide an accurate picture of the project's current state.

### Tier 2: Medium-Term Priorities (Next 1-3 Months)

These items focus on the most important new features and data sources.

1.  **Integrate FMCS Contract Expiration Data:** This is the highest-value new data source.
2.  **Implement NLRB Real-Time Monitoring:** This will provide highly actionable intelligence for organizers.
3.  **Refactor the scripts/etl/ directory:** Reorganize the ETL scripts and create a simple orchestration script to define the data pipeline as code.
4.  **Adopt a Production-Ready Rate Limiter:** Replace the in-memory rate limiter with a solution that uses a shared store like Redis.
5.  **Begin Frontend Migration to React/Vue:** Start building new features in a modern frontend framework and begin to strangle the old monolith.

### Tier 3: Long-Term Priorities (Next 3-6 Months)

These items are strategic investments that will pay off in the long run.

1.  **Adopt splink for all matching:** Move to a probabilistic matching model for all data sources.
2.  **Build a Predictive Model:** Replace the heuristic scorecard with a data-driven predictive model, following the excellent plan in the roadmap.
3.  **Implement a Staging Environment:** Set up a proper staging environment for testing before deploying to production.
4.  **Adopt Infrastructure as Code (IaC):** Manage the cloud infrastructure with a tool like Terraform.
5.  **Implement a Component Library:** Use a component library like Material-UI to accelerate frontend development.
