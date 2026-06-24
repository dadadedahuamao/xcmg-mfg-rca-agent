param(
    [string]$BaseUrl = "http://localhost:11434",
    [string]$Model = "dengcao/Qwen3-Reranker-4B:Q4_K_M",
    [int]$TimeoutSec = 600
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message"
}

function Get-JsonArrayFromText {
    param([string]$Text)

    $match = [regex]::Match($Text, '(?s)\[\s*\{.*?\}\s*\]')
    if (-not $match.Success) {
        return $null
    }

    try {
        return $match.Value | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

Write-Step "Check Ollama service"
$tagsUrl = "$BaseUrl/api/tags"
$tags = Invoke-RestMethod -Method Get -Uri $tagsUrl -TimeoutSec 10

$modelNames = @($tags.models | ForEach-Object { $_.name })
if ($modelNames -notcontains $Model) {
    Write-Host "Model not found: $Model"
    Write-Host "Available models:"
    $modelNames | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "Model found: $Model"

Write-Step "Build rerank test request"
$query = "WS-05 scheduling delay with equipment maintenance not completed. Which candidate is most relevant?"
$candidates = @(
    [pscustomobject]@{
        id = "doc_a"
        title = "WS-05 equipment maintenance and scheduling conflict"
        content = "WS-05 has EQ-002 spindle accuracy deviation and EQ-005 tool magazine failure. Multiple high-priority work orders are waiting, causing scheduling conflict risk."
    },
    [pscustomobject]@{
        id = "doc_b"
        title = "MES-WMS interface timeout handling"
        content = "When MES-WMS has Timeout or Gateway Timeout, check network, retry policy, and inventory synchronization delay."
    },
    [pscustomobject]@{
        id = "doc_c"
        title = "Material safety stock warning"
        content = "When material inventory is below safety stock, check kitting status, purchase arrival plan, and substitute material strategy."
    }
)

$candidateText = ($candidates | ConvertTo-Json -Depth 5)
$prompt = @"
You are a manufacturing RAG reranker.
Rank candidates by relevance to the query.

Rules:
1. Output JSON array only. No markdown. No explanation outside JSON.
2. Sort by relevance descending.
3. Each item must contain id, score, reason.
4. score must be a number between 0 and 1.

query:
$query

candidates:
$candidateText
"@

$body = @{
    model = $Model
    prompt = $prompt
    stream = $false
    options = @{
        temperature = 0
        num_predict = 256
    }
} | ConvertTo-Json -Depth 10

Write-Step "Call Ollama generate API"
$generateUrl = "$BaseUrl/api/generate"
$response = Invoke-RestMethod -Method Post -Uri $generateUrl -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec $TimeoutSec

Write-Step "Raw model output"
Write-Host $response.response

$ranked = Get-JsonArrayFromText -Text $response.response
if ($null -eq $ranked) {
    Write-Host "Failed to parse JSON array from model output."
    exit 2
}

Write-Step "Parsed ranking"
$ranked | Format-Table id, score, reason -AutoSize

$topId = @($ranked)[0].id
if ($topId -ne "doc_a") {
    Write-Host "Test failed: expected top candidate doc_a, actual top candidate $topId"
    exit 3
}

Write-Step "Test passed"
Write-Host "Ollama reranker model returned the expected top candidate."
