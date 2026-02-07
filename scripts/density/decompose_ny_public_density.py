"""
Decompose NY Public Sector Union Density by Government Level

Given:
- NY public sector density: 65.2%
- NY workforce shares: Federal 2.1%, State 4.2%, Local 10.3%
- National densities: Federal 25.3%, State 27.8%, Local 38.2%

Problem: One equation, three unknowns:
  65.2% = (Fed_Share × Fed_Density + State_Share × State_Density + Local_Share × Local_Density) / Public_Share

Approach: Assume NY has a uniform "union premium" multiplier across all government levels
"""

# NY Workforce Shares (% of total workforce)
NY_FED_SHARE = 0.021      # 2.1%
NY_STATE_SHARE = 0.042    # 4.2%
NY_LOCAL_SHARE = 0.103    # 10.3%
NY_PUBLIC_SHARE = NY_FED_SHARE + NY_STATE_SHARE + NY_LOCAL_SHARE  # 16.6%

NY_PRIVATE_SHARE = 0.776  # 77.6%
NY_SELF_EMP_SHARE = 0.055 # 5.5%

# Known NY Densities
NY_PRIVATE_DENSITY = 12.4
NY_PUBLIC_DENSITY = 65.2
NY_TOTAL_DENSITY = 21.3

# National Government Densities (2024)
NAT_FED_DENSITY = 25.3
NAT_STATE_DENSITY = 27.8
NAT_LOCAL_DENSITY = 38.2

print("=" * 75)
print("DECOMPOSING NY PUBLIC SECTOR UNION DENSITY")
print("=" * 75)

# Calculate shares within public sector
fed_share_of_public = NY_FED_SHARE / NY_PUBLIC_SHARE
state_share_of_public = NY_STATE_SHARE / NY_PUBLIC_SHARE
local_share_of_public = NY_LOCAL_SHARE / NY_PUBLIC_SHARE

print("\n1. NY WORKFORCE COMPOSITION")
print("-" * 40)
print(f"   Federal:      {NY_FED_SHARE*100:5.1f}% of total ({fed_share_of_public*100:5.1f}% of public)")
print(f"   State:        {NY_STATE_SHARE*100:5.1f}% of total ({state_share_of_public*100:5.1f}% of public)")
print(f"   Local:        {NY_LOCAL_SHARE*100:5.1f}% of total ({local_share_of_public*100:5.1f}% of public)")
print(f"   Public Total: {NY_PUBLIC_SHARE*100:5.1f}% of total")
print(f"   Private:      {NY_PRIVATE_SHARE*100:5.1f}% of total")
print(f"   Self-Employed:{NY_SELF_EMP_SHARE*100:5.1f}% of total (0% union rate)")

print("\n2. KNOWN DENSITIES")
print("-" * 40)
print(f"   NY Private Sector:  {NY_PRIVATE_DENSITY:5.1f}%")
print(f"   NY Public Sector:   {NY_PUBLIC_DENSITY:5.1f}%")
print(f"   NY Total:           {NY_TOTAL_DENSITY:5.1f}%")
print(f"\n   National Federal:   {NAT_FED_DENSITY:5.1f}%")
print(f"   National State:     {NAT_STATE_DENSITY:5.1f}%")
print(f"   National Local:     {NAT_LOCAL_DENSITY:5.1f}%")

# Calculate national weighted average for comparison
nat_public_density_implied = (
    fed_share_of_public * NAT_FED_DENSITY +
    state_share_of_public * NAT_STATE_DENSITY +
    local_share_of_public * NAT_LOCAL_DENSITY
)
print(f"\n   National public (if NY composition): {nat_public_density_implied:5.1f}%")

print("\n3. UNIFORM MULTIPLIER APPROACH")
print("-" * 40)
print("   Assumption: NY is uniformly more union-dense by factor k")
print("   Fed_NY = k × 25.3%, State_NY = k × 27.8%, Local_NY = k × 38.2%")

# Solve for k
# NY_PUBLIC_DENSITY = fed_share × (k × NAT_FED) + state_share × (k × NAT_STATE) + local_share × (k × NAT_LOCAL)
# NY_PUBLIC_DENSITY = k × (fed_share × NAT_FED + state_share × NAT_STATE + local_share × NAT_LOCAL)

weighted_national = (
    fed_share_of_public * NAT_FED_DENSITY +
    state_share_of_public * NAT_STATE_DENSITY +
    local_share_of_public * NAT_LOCAL_DENSITY
)

k = NY_PUBLIC_DENSITY / weighted_national

print(f"\n   Weighted national avg: {weighted_national:.2f}%")
print(f"   NY multiplier (k):     {k:.3f}x")

# Calculate estimated NY densities
ny_fed_est = k * NAT_FED_DENSITY
ny_state_est = k * NAT_STATE_DENSITY
ny_local_est = k * NAT_LOCAL_DENSITY

print(f"\n   ESTIMATED NY DENSITIES:")
print(f"   {'Level':10} | {'National':10} | {'NY Est':10} | {'Multiplier':10}")
print(f"   {'-'*10} | {'-'*10} | {'-'*10} | {'-'*10}")
print(f"   {'Federal':10} | {NAT_FED_DENSITY:9.1f}% | {ny_fed_est:9.1f}% | {k:.2f}x")
print(f"   {'State':10} | {NAT_STATE_DENSITY:9.1f}% | {ny_state_est:9.1f}% | {k:.2f}x")
print(f"   {'Local':10} | {NAT_LOCAL_DENSITY:9.1f}% | {ny_local_est:9.1f}% | {k:.2f}x")

# Verify
verification = (
    fed_share_of_public * ny_fed_est +
    state_share_of_public * ny_state_est +
    local_share_of_public * ny_local_est
)
print(f"\n   Verification: {verification:.1f}% (target: {NY_PUBLIC_DENSITY}%)")

print("\n4. ALTERNATIVE: LOCAL-HEAVY SCENARIO")
print("-" * 40)
print("   Assumption: Federal workers are harder to organize (federal law)")
print("   Let Federal = 1.5x national, State = 1.8x, Local = 2.1x")

alt_fed_mult = 1.5
alt_state_mult = 1.8

# Solve for local multiplier to hit 65.2%
# 65.2 = fed_share × (1.5 × 25.3) + state_share × (1.8 × 27.8) + local_share × (? × 38.2)
fed_contrib = fed_share_of_public * (alt_fed_mult * NAT_FED_DENSITY)
state_contrib = state_share_of_public * (alt_state_mult * NAT_STATE_DENSITY)
remaining = NY_PUBLIC_DENSITY - fed_contrib - state_contrib
alt_local_density = remaining / local_share_of_public
alt_local_mult = alt_local_density / NAT_LOCAL_DENSITY

print(f"   Federal:  {alt_fed_mult:.1f}x × {NAT_FED_DENSITY}% = {alt_fed_mult * NAT_FED_DENSITY:.1f}%")
print(f"   State:    {alt_state_mult:.1f}x × {NAT_STATE_DENSITY}% = {alt_state_mult * NAT_STATE_DENSITY:.1f}%")
print(f"   Local:    {alt_local_mult:.2f}x × {NAT_LOCAL_DENSITY}% = {alt_local_density:.1f}%")

# Verify
alt_verification = (
    fed_share_of_public * (alt_fed_mult * NAT_FED_DENSITY) +
    state_share_of_public * (alt_state_mult * NAT_STATE_DENSITY) +
    local_share_of_public * alt_local_density
)
print(f"\n   Verification: {alt_verification:.1f}% (target: {NY_PUBLIC_DENSITY}%)")

print("\n5. CONTRIBUTION BREAKDOWN (Using Uniform Multiplier)")
print("-" * 40)

fed_members_pct = fed_share_of_public * ny_fed_est
state_members_pct = state_share_of_public * ny_state_est
local_members_pct = local_share_of_public * ny_local_est

print(f"   Level    | Share of Public | Density | Contribution to 65.2%")
print(f"   -------- | --------------- | ------- | ---------------------")
print(f"   Federal  | {fed_share_of_public*100:14.1f}% | {ny_fed_est:6.1f}% | {fed_members_pct:5.1f}% ({fed_members_pct/NY_PUBLIC_DENSITY*100:.1f}% of total)")
print(f"   State    | {state_share_of_public*100:14.1f}% | {ny_state_est:6.1f}% | {state_members_pct:5.1f}% ({state_members_pct/NY_PUBLIC_DENSITY*100:.1f}% of total)")
print(f"   Local    | {local_share_of_public*100:14.1f}% | {ny_local_est:6.1f}% | {local_members_pct:5.1f}% ({local_members_pct/NY_PUBLIC_DENSITY*100:.1f}% of total)")
print(f"   -------- | --------------- | ------- | ---------------------")
print(f"   Total    | {100:14.1f}% |         | {NY_PUBLIC_DENSITY:5.1f}%")

print("\n6. FULL WORKFORCE DENSITY CHECK")
print("-" * 40)
# Total = Private_Share × Private_Density + Public breakdown + Self_Emp × 0
total_calc = (
    NY_PRIVATE_SHARE * NY_PRIVATE_DENSITY +
    NY_FED_SHARE * ny_fed_est +
    NY_STATE_SHARE * ny_state_est +
    NY_LOCAL_SHARE * ny_local_est +
    NY_SELF_EMP_SHARE * 0
)
print(f"   Private:      {NY_PRIVATE_SHARE*100:.1f}% × {NY_PRIVATE_DENSITY:.1f}% = {NY_PRIVATE_SHARE * NY_PRIVATE_DENSITY:.2f}%")
print(f"   Federal:      {NY_FED_SHARE*100:.1f}% × {ny_fed_est:.1f}% = {NY_FED_SHARE * ny_fed_est:.2f}%")
print(f"   State:        {NY_STATE_SHARE*100:.1f}% × {ny_state_est:.1f}% = {NY_STATE_SHARE * ny_state_est:.2f}%")
print(f"   Local:        {NY_LOCAL_SHARE*100:.1f}% × {ny_local_est:.1f}% = {NY_LOCAL_SHARE * ny_local_est:.2f}%")
print(f"   Self-Emp:     {NY_SELF_EMP_SHARE*100:.1f}% × 0% = 0.00%")
print(f"   ----------------------------------------")
print(f"   Calculated Total: {total_calc:.1f}%")
print(f"   Actual Total:     {NY_TOTAL_DENSITY:.1f}%")
print(f"   Difference:       {abs(total_calc - NY_TOTAL_DENSITY):.2f}%")

print("\n" + "=" * 75)
print("SUMMARY: ESTIMATED NY PUBLIC SECTOR DENSITY BY LEVEL")
print("=" * 75)
print(f"""
Using uniform multiplier assumption (NY is {k:.2f}x national at all levels):

   Level     | NY Estimate | National | NY Premium
   --------- | ----------- | -------- | ----------
   Federal   |    {ny_fed_est:5.1f}%   |  {NAT_FED_DENSITY:5.1f}%  | +{ny_fed_est - NAT_FED_DENSITY:.1f}%
   State     |    {ny_state_est:5.1f}%   |  {NAT_STATE_DENSITY:5.1f}%  | +{ny_state_est - NAT_STATE_DENSITY:.1f}%
   Local     |    {ny_local_est:5.1f}%   |  {NAT_LOCAL_DENSITY:5.1f}%  | +{ny_local_est - NAT_LOCAL_DENSITY:.1f}%

Note: These are estimates. The actual decomposition requires state-level
CPS microdata that isn't publicly available for small subgroups.
""")
