# Stress/Sweep Test for Workload Generator
# Usage: ./sweep.ps1 [factory_url]

$factory_url = if ($args[0]) { $args[0] } else { "http://localhost:8000" }

Write-Host "Starting Stress Sweep against $factory_url" -ForegroundColor Cyan

# 1. Depth Sweep (1 to 10)
Write-Host "Running Depth Sweep (1-10)..."
workload measure --factory-url $factory_url --workload depth --range 1-10 --runs 5 --warmup-runs 1

# 2. Fan-out Sweep (1 to 20)
Write-Host "Running Fan-out Sweep (1-20)..."
workload measure --factory-url $factory_url --workload fanout --range 1-20 --runs 5 --warmup-runs 1

# 3. Issue/Resolve sanity checks
Write-Host "Running Issue/Resolve sanity checks..."
workload measure --factory-url $factory_url --workload issue --range 1-5 --runs 3 --warmup-runs 1
workload measure --factory-url $factory_url --workload resolve --range 1-5 --runs 3 --warmup-runs 1

Write-Host "Sweep complete. Check output/ directory for results." -ForegroundColor Green
