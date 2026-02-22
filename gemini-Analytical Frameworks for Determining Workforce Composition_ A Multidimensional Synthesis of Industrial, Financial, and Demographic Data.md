# **Analytical Frameworks for Determining Workforce Composition: A Multidimensional Synthesis of Industrial, Financial, and Demographic Data**

The systematic determination of workforce composition within specialized business entities requires an integrated approach that leverages federal economic taxonomies, establishment-level financial surveys, and individual-level demographic datasets. For researchers, industry analysts, and policy planners, the ability to reconstruct the labor architecture of a specific firm—based on parameters such as its North American Industry Classification System (NAICS) code, annual revenue, and geographic location—is a critical competency. This report provides a comprehensive methodology for this reconstruction, utilizing the Bureau of Labor Statistics (BLS) and U.S. Census Bureau frameworks to model the internal staffing of complex organizations, such as private security firms and specialized nursing facilities.

## **Theoretical Foundations of Industrial and Occupational Classification**

At the core of workforce analytics lies the North American Industry Classification System (NAICS), a hierarchical structure used across the federal government to group business establishments into industries based on their primary production processes or service delivery models. The NAICS framework is updated periodically to reflect the evolving nature of the North American economy, with the most recent versions providing increased granularity in service-oriented sectors such as information, professional services, and healthcare.

### **The Hierarchical Structure of NAICS**

Understanding the depth of a NAICS code is the first step in identifying a firm's specialized workforce. The system uses a six-digit coding structure that provides five levels of classification, which is a significant expansion over the four-digit Standard Industrial Classification (SIC) system it replaced.

| Classification Level | Digits | Example (Nursing Homes) | Application in Workforce Modeling |
| :---- | :---- | :---- | :---- |
| Sector | 2 | 62 (Health Care) | Defines the broad labor market and regulatory environment. |
| Subsector | 3 | 623 (Nursing/Residential Care) | Identifies general facility-based care requirements and staffing trends. |
| Industry Group | 4 | 6231 (Nursing Care Facilities) | Focuses on clinical inpatient environments as opposed to community-based care. |
| NAICS Industry | 5 | 62311 (Nursing Care Facilities) | Provides comparable data across the U.S., Canada, and Mexico. |
| U.S. Industry | 6 | 623110 (Skilled Nursing Facilities) | The primary unit for specialized modeling and specific demographic analysis. |

The numeric system allows for precise differentiation between industries that may appear similar but have vastly different labor-to-capital ratios. For example, in the security sector, a clear distinction is made between NAICS 561612 (Security Guards and Patrol Services) and NAICS 561621 (Security Systems Services), where the former is labor-intensive and the latter is technology-intensive.

### **The Standard Occupational Classification (SOC) System**

To bridge the gap between "what the company does" and "what the people do," researchers utilize the Standard Occupational Classification (SOC) system. While NAICS classifies the establishment, SOC classifies the job based on duties and required skills. The 2018 SOC system, utilized by the May 2024 OEWS estimates, consists of approximately 830 detailed occupations. The mapping of SOC codes onto NAICS industries—known as a staffing pattern—is the mechanism by which analysts determine the specific types of jobs present in a specialized nursing home or a private security firm.

## **Methodologies for Estimating Total Headcount from Revenue**

A primary challenge in private sector research is estimating the number of employees for a firm where only financial data, such as annual revenue or sales, is available. The U.S. Census Bureau’s Statistics of U.S. Businesses (SUSB) program provides the necessary empirical link between receipts and employment size.

### **The SUSB and the Business Register**

The SUSB is a compilation of data extracted from the Census Bureau's Business Register (BR), which is a continuously updated database incorporating federal tax records, economic censuses, and departmental statistics. The SUSB provides annual data by geographic area, industry detail, and enterprise size, including the number of firms, establishments, payroll, and employment. For years ending in 2 and 7 (Economic Census years), the SUSB includes estimated receipts data, which allows for the calculation of revenue-per-employee metrics.

### **Mathematical Modeling of Employment Volume**

To estimate the headcount ($E$) for a firm with a known annual revenue ($R$), analysts apply an industry-specific productivity coefficient ($\\rho$), representing the average revenue generated per employee.

$$E \= \\frac{R}{\\rho}$$  
The coefficient $\\rho$ is not static; it varies significantly by industry and firm size. In labor-intensive sectors like security services, $\\rho$ is relatively low, whereas in capital-intensive sectors like utility management, it is markedly higher.

#### **Case Study: Private Security Firm Revenue-to-Employment**

In the security guard and patrol services industry (NAICS 561612), historical data from 2017 indicated a total industry revenue of $\\$29,545,237,000$ and total employment of 752,130 people. This yields a baseline revenue-per-employee of approximately $\\$39,282$. However, recent market analysis suggests that inflation and rising wages have pushed this figure higher. For active, mid-sized firms in 2024, the average revenue per employee is estimated at $\\$47,944$.

For a security firm in Atlanta with $\\$40$ million in annual revenue, the estimated headcount ranges based on the productivity model used:

| Productivity Metric | Source | Estimated Headcount ($40M Revenue) |
| :---- | :---- | :---- |
| Historical Baseline ($39,282) | Census 2017 | 1,018 Employees |
| Active Market Rate ($47,944) | Kentley Insights 2024 | 834 Employees |
| Large Firm Average ($4.8M/99 workers) | Vertical IQ | 825 Employees |

The convergence of modern market rates and large-firm averages suggests that a $\\$40$ million revenue firm likely employs between 825 and 835 individuals. This size places the firm well above the SBA’s small business size standard for this industry, which is capped at $\\$22$ million in annual revenue.

## **Staffing Matrix Analysis: Identifying Occupational Concentrations**

Once the total workforce size is estimated, the next phase of the research involves distributing that headcount into specific job categories. This is accomplished using Occupational Employment and Wage Statistics (OEWS) staffing patterns, which provide the percentage distribution of occupations within a 4-digit or 6-digit NAICS industry.

### **Modeling the Atlanta Security Firm Workforce (NAICS 561612\)**

The staffing pattern for NAICS 561612 is characterized by high concentration in a single protective service occupation, supplemented by supervisory and administrative layers. The Atlanta-Sandy Springs-Roswell, GA MSA has a significant security presence, with 22,320 guards employed across the region, reflecting a mature market for these services.

| SOC Code | Occupation Title | % of Industry | Est. Count ($40M Firm) | Primary Responsibilities |
| :---- | :---- | :---- | :---- | :---- |
| 33-9032 | Security Guards | 73.69% | 614 | Front-line protection, patrolling, and access control. |
| 33-1090 | First-Line Supervisors | \~5.0% | 42 | Direct oversight of guard deployments and scheduling. |
| 43-0000 | Administrative Support | \~10.0% | 83 | Payroll, billing, and general office clerical work. |
| 11-1021 | Operations Managers | 0.48% | 4 | High-level strategy and client relationship management. |
| 11-9199 | Managers, All Other | 0.32% | 3 | Specialized administrative or technical leadership. |
| 13-0000 | Business/Finance Ops | 0.90% | 7 | Accounting, human resources, and recruitment. |

The high volume of guards relative to management (a ratio of approximately 14:1) is indicative of a "flat" organizational structure common in service-contracting firms. In a $\\$40$ million enterprise, the administrative and recruiting functions (SOC 13-0000 and 43-0000) are critical, as high turnover in the security sector necessitates a continuous hiring pipeline.

### **Modeling the Specialized Nursing Home Workforce (NAICS 623110\)**

Specialized nursing homes, categorized under NAICS 623110 (Nursing Care Facilities), exhibit a more complex staffing matrix due to clinical necessity and regulatory mandates. Revenue in this sector is often modeled per bed; a 120-bed community typically generates $\\$13.4$ million in revenue. Therefore, a $\\$40$ million revenue facility would likely be a large-scale campus with approximately 350 to 360 beds, or a highly specialized rehabilitative center with a high-acuity patient mix.

The staffing distribution in such a facility is dominated by healthcare support roles, which are subject to proposed CMS minimum staffing standards, such as 0.55 RN hours per resident day (HPRD) and 2.45 NA HPRD.

| SOC Code | Occupation Title | % of Workforce | Key Function within Facility |
| :---- | :---- | :---- | :---- |
| 31-1131 | Nursing Assistants | 33.25% \- 37.0% | Core daily care and patient monitoring. |
| 29-2061 | LPNs and LVNs | 12.42% \- 13.0% | Clinical care and medication administration. |
| 29-1141 | Registered Nurses | 9.01% \- 9.0% | Advanced clinical oversight and care planning. |
| 35-0000 | Food Prep/Serving | \~10.0% | Specialized dietary management. |
| 11-9111 | Health Services Managers | 2.04% | Regulatory compliance and facility administration. |
| 21-1022 | Healthcare Social Workers | 1.08% | Family coordination and admissions. |
| 37-0000 | Maintenance/Cleaning | \~8.0% | Infection control and facility upkeep. |

In a specialized nursing home, the "Practitioner" group (SOC 29-0000) often includes a higher percentage of specialized therapists (Physical, Occupational, and Speech) compared to standard long-term care homes, reflecting the higher-acuity rehabilitative services that generate higher revenue per patient.

## **Demographic Profiling: Analyzing the Workforce Occupants**

Understanding who occupies these jobs requires the synthesis of American Community Survey (ACS) data, which provides demographic and socioeconomic characteristics by detailed occupation. The ACS uses a system of 569 occupational categories, mapped from write-in responses to household surveys.

### **The Human Profile of the Security Workforce (SOC 33-9032)**

Security guards are most commonly men and workers of color, particularly in large urban MSAs. Data from major metropolitan areas such as New York and Baltimore provide high-fidelity proxies for the Atlanta market.

| Demographic Characteristic | Security Guard Profile (SOC 33-9032) | Context and Implications |
| :---- | :---- | :---- |
| **Gender (Sex)** | 65.8% to 77.3% Male | Strong male skew, though female representation is higher in low-wage tiers (27%). |
| **Race/Ethnicity** | 50.8% to 73.3% Black/African American | Significant overrepresentation of Black workers relative to the general labor force. |
| **Median Age** | 38 to 42 Years | A mature workforce, with 35.6% in the "prime" 40-54 age bracket. |
| **Education** | 47.1% to 62.5% Post-Secondary | Higher than expected educational attainment, including some college or degrees. |
| **Citizenship** | \~44.7% Foreign Born (NYC Data) | Reflects the role of the security industry as an entry point for immigrant labor. |

In the Atlanta MSA specifically, the workforce is likely to mirror these trends, given the region's demographic profile where Black or African American residents constitute a significant portion of the population (e.g., 49.5k in Southwest GA PUMA alone).

### **The Human Profile of the Nursing Assistant Workforce (SOC 31-1131)**

The demographics of nursing assistants in specialized nursing homes are among the most concentrated in the U.S. economy. This workforce is overwhelmingly female and increasingly reliant on immigrant and minority labor.

* **Gender**: 91% of nursing assistants in nursing homes are female.  
* **Race**: Black or African American workers account for 35% of the workforce, with White workers at 47% and Hispanic workers at 10%.  
* **Educational Attainment**: 51% have a high school degree or less, while 43% have some college education but no degree.  
* **Economic Status**: 37% of direct care workers live in or near poverty, and 45% rely on some form of public assistance.

This demographic profile indicates that the "who" of the nursing home workforce is often a population facing systemic economic challenges, which has direct implications for recruitment and retention in high-revenue facilities.

## **Geospatial Variations and Data Availability**

The ability to find this data at the ZIP code, MSA, or state level is governed by the Census Bureau's "disclosure avoidance" protocols. While the methodology for finding the data is consistent, the availability of specific data points varies by the size of the geographic unit.

### **The Hierarchy of Geographic Granularity**

Researchers must navigate different tools depending on the level of geographic detail required.

1. **Metropolitan Statistical Area (MSA)**: This is the most reliable level for detailed industry-specific occupational data. The OEWS program publishes cross-industry estimates for approximately 530 MSAs. In the Atlanta-Sandy Springs-Roswell, GA MSA, for instance, detailed wage and employment counts for security guards (SOC 33-9032) are readily available.  
2. **State and Region**: Ideal for understanding broader policy impacts, such as Medicaid expansion's effect on nursing assistants or state-specific licensing for security.  
3. **ZIP Code and Census Tract**: Available through the Census Business Builder (CBB) for demographic data (customers) but frequently suppressed for business data (competitors).

### **Privacy Suppression and "Greyed Out" Data**

A critical insight for researchers is the Census Bureau’s Tip \#2: "There's No Business Data by Neighborhood". To protect the privacy of individual firms, business variables such as employment, payroll, and sales are withheld if there are very few companies in a given industry within a specific ZIP code. When using the CBB, these variables often appear "greyed out." Analysts are encouraged to "start broad" at the County or MSA level before attempting to drill down to ZIP codes.

## **Economic Drivers and the Regulatory Environment**

The workforce composition of a large firm is not merely a product of market forces; it is heavily influenced by federal contracting rules and industry-specific regulations.

### **SBA Size Standards and the 24-Month Rule**

The Small Business Administration (SBA) uses NAICS codes to set size standards that determine eligibility for federal contracts. For most industries, the SBA has transitioned to a 24-month averaging period for calculating a firm’s number of employees.

| SBA Size Standard Parameter | NAICS 561612 (Security) | NAICS 623110 (Nursing) |
| :---- | :---- | :---- |
| **Primary Metric** | Annual Revenue | Annual Revenue |
| **Small Business Limit** | $22.0 Million | $34.0 Million |
| **Status of $40M Firm** | Other than Small | Other than Small |

A firm with $\\$40$ million in revenue in either of these industries would be competing in the "Full and Open" market, where they are required to maintain more robust compliance, human resources, and reporting structures than their small-business counterparts.

### **Federal Contract Spending and Workforce Scaling**

In the private security sector, federal contracts are a major driver of workforce scaling. Total federal contract spending for NAICS 561612 reached $\\$5.56$ billion in 2023\. For a large firm in Atlanta, securing a contract like the Department of Justice's $\\$170.3$ million guard services award would necessitate an immediate and massive expansion of the front-line guard workforce, likely utilizing temporary help services or specialized recruitment agencies.

## **Synthesis: Modeling the $40 Million Atlanta Security Firm**

To conclude the analysis with the specific example requested: a private security firm in Atlanta, Georgia, with $\\$40$ million in annual revenue.

**Total Workforce Projection**: 833 to 840 Employees.

### **Occupational Breakdown and Demographics**

| Job Title | Estimated Quantity | Most Likely Demographic Profile |
| :---- | :---- | :---- |
| **Security Guards** | 614 | Male (75%), Black/African American (60%+ in ATL), Median Age 38, High School/Some College. |
| **First-Line Supervisors** | 42 | Male, older (45-55), likely prior military or police experience. |
| **Office/Admin Support** | 83 | Female, mixed race, high school degree. |
| **Operations/General Managers** | 4 | Mixed gender, Bachelor's degree or higher, 10+ years experience. |
| **HR/Recruiting/Payroll** | 12 | Female-dominated, focused on high-volume background checks and Ohio/Georgia firearm permits. |

The "who" of this workforce is deeply tied to the urban labor market of the Atlanta MSA. The firm would likely have a central headquarters in the metropolitan area, possibly near the Hartsfield-Jackson airport or the federal facilities it services, and would draw from a labor pool where the location quotient for security guards is 1.00—meaning the supply of labor is perfectly proportional to the national average, though the wages ($18.13/hr) are slightly lower than national peaks.

## **Conclusion**

Determining the workforce composition of specialized firms is a process of triangulation. By identifying the NAICS code, the researcher establishes the industry's baseline staffing matrix and regulatory constraints. By applying revenue-per-employee coefficients from the SUSB, the analyst estimates the total scale of the labor force. Finally, by integrating ACS demographic data and MSA-specific labor statistics, a detailed profile of the workers themselves—their age, gender, race, and education—is constructed. This methodology transforms static financial figures into a dynamic, human-centric model of organizational life, providing a critical tool for strategic and economic analysis.

