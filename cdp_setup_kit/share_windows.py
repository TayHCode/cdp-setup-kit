"""Auditable PowerShell: protected ledger plus exact resource matching."""
import ipaddress
import json
import re

from .constants import APP_NAME, LOOPBACK


def quote(value):
    return "'" + re.sub("'", "''", value) + "'"


COMMON = r'''
$ErrorActionPreference = 'Stop'
$persistentStore = @{ PolicyStore = 'PersistentStore' }
$activeStore = @{ PolicyStore = 'ActiveStore' }
$root = Join-Path $env:ProgramData 'cdp-setup-kit-shares'
function SafePath($path) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refused reparse point: $path" }
    }
}
SafePath $env:ProgramData
SafePath $root
function SafeLedger($path) {
    SafePath $path
    if (Test-Path -LiteralPath $path) {
        $acl = Get-Acl -LiteralPath $path
        $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        if ($ownerSid -notin @('S-1-5-18','S-1-5-32-544')) { throw 'Refused machine ledger with non-admin owner' }
        foreach ($ace in $acl.Access) {
            $sid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            $write = [Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
            if ($ace.AccessControlType -eq 'Allow' -and ($ace.FileSystemRights -band $write) -and $sid -notin @('S-1-5-18','S-1-5-32-544')) { throw 'Refused writable machine ledger' }
        }
    }
}
SafeLedger $root
function ProxyValue($addr, $port) {
    $registryPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp'
    if (Test-Path $registryPath) {
        $v = Get-ItemProperty -LiteralPath $registryPath
        return $v.PSObject.Properties["$addr/$port"].Value
    }
    return $null
}
function CheckProxy($r, $owned) {
    $base = 'HKLM:\SYSTEM\CurrentControlSet\Services\PortProxy'
    if (Test-Path $base) {
        foreach ($registryPath in @(Get-ChildItem $base -Recurse | Where-Object { $_.PSChildName -eq 'tcp' })) {
            foreach ($v in (Get-ItemProperty $registryPath.PSPath).PSObject.Properties) {
                if ($v.Name -match ('/' + $r.port + '$')) {
                    if (-not $owned -or $registryPath.Name -notmatch '\\v4tov4\\tcp$' -or $v.Name -ne ($r.address + '/' + $r.port) -or $v.Value -ne ('@LOOPBACK@/' + $r.port)) {
                        throw 'Refused existing or changed portproxy on this port; no entries adopted or overwritten'
                    }
                }
            }
        }
    }
}
function Matches($actual, $expected) {
    function Normal($item) {
        $text = [string]$item
        if ($text -match '^(\d+\.\d+\.\d+\.\d+)/(\d{1,2})$') {
            $base = $Matches[1]
            $prefix = [int]$Matches[2]
            if ($prefix -eq 32) { return $base }
            $mask = @(0..3 | ForEach-Object { $bits = [Math]::Min(8, [Math]::Max(0, $prefix - 8 * $_)); [string](256 - [Math]::Pow(2, 8 - $bits)) }) -join '.'
            return "$base/$mask"
        }
        return $text
    }
    return ((@($actual | ForEach-Object { Normal $_ } | Sort-Object) -join ',') -eq (@($expected | ForEach-Object { Normal $_ } | Sort-Object) -join ','))
}
function CheckResources($r, $folder, $description) {
    CheckProxy $r $true
    $rule = Get-NetFirewallRule @persistentStore -Name $r.marker -ErrorAction SilentlyContinue
    if ($rule) {
        $p = $rule | Get-NetFirewallPortFilter
        $a = $rule | Get-NetFirewallAddressFilter
        $i = $rule | Get-NetFirewallInterfaceFilter
        if ($rule.Description -ne $description -or $rule.Direction -ne 'Inbound' -or $rule.Action -ne 'Allow' -or $rule.Enabled -ne 'True' -or $p.Protocol -ne 'TCP' -or -not (Matches $p.LocalPort @([string]$r.port)) -or -not (Matches $a.LocalAddress @($r.address)) -or -not (Matches $a.RemoteAddress $r.peers) -or -not (Matches $i.InterfaceAlias @($r.interface))) {
            throw 'Refused foreign or changed firewall rule'
        }
    }
    $deny = Get-NetFirewallRule @persistentStore -Name ($r.marker + '-deny') -ErrorAction SilentlyContinue
    if ($deny) {
        $p = $deny | Get-NetFirewallPortFilter
        $a = $deny | Get-NetFirewallAddressFilter
        $i = $deny | Get-NetFirewallInterfaceFilter
        if ($deny.Description -ne $description -or $deny.Direction -ne 'Inbound' -or $deny.Action -ne 'Block' -or $deny.Enabled -ne 'True' -or $p.Protocol -ne 'TCP' -or -not (Matches $p.LocalPort @([string]$r.port)) -or -not (Matches $a.LocalAddress @($r.address)) -or -not (Matches $a.RemoteAddress $r.denied) -or -not (Matches $i.InterfaceAlias @($r.interface))) {
            throw 'Refused foreign or changed companion block rule'
        }
    }
    $task = Get-ScheduledTask -TaskName ($r.marker + '-refresh') -ErrorAction SilentlyContinue
    if ($task) {
        $expected = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $folder 'refresh.ps1') + '"'
        if ($task.Description -ne $description -or @($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ne 'powershell.exe' -or $task.Actions[0].Arguments -ne $expected -or $task.Principal.UserId -notin @('SYSTEM', 'S-1-5-18')) {
            throw 'Refused foreign or changed refresh task'
        }
    }
}
function Netsh($argsList) {
    & netsh.exe @argsList | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "netsh failed: $LASTEXITCODE" }
}
function CheckFirewall($r) {
    foreach ($f in @(Get-NetFirewallProfile @activeStore)) {
        if (-not $f.Enabled -or $f.DefaultInboundAction -eq 'Allow' -or $f.AllowInboundRules -eq 'False') {
            throw 'Requires enabled Windows Firewall with inbound default Block and local rules allowed; no firewall policy is changed'
        }
    }

}
'''

REFRESH = r'''
@COMMON@
$folder = Split-Path -Parent $PSCommandPath
SafeLedger $folder
SafeLedger (Join-Path $folder 'state.json')
$r = Get-Content -Raw -LiteralPath (Join-Path $folder 'state.json') | ConvertFrom-Json
$description = 'cdp-setup-kit owned share v1: ' + $r.owner + ' / ' + $r.marker
CheckResources $r $folder $description
CheckFirewall $r
if (-not (Get-NetFirewallRule -Name $r.marker -ErrorAction SilentlyContinue) -or -not (Get-NetFirewallRule -Name ($r.marker + '-deny') -ErrorAction SilentlyContinue)) { throw 'Owned firewall rule missing; refusing to refresh' }
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $r.address -ErrorAction SilentlyContinue
    if ($ip -and $ip.InterfaceAlias -eq $r.interface) {
        CheckProxy $r $true
        Netsh @('interface','portproxy','add','v4tov4',('listenaddress=' + $r.address),('listenport=' + $r.port),'connectaddress=@LOOPBACK@',('connectport=' + $r.port),'protocol=tcp')
        exit 0
    }
    Start-Sleep -Seconds 3
}
throw 'Shared address not present on its recorded interface; refusing to bind elsewhere'
'''

MUTATE = r'''
@COMMON@
$marker = @MARKER@
$owner = @OWNER@
$action = @ACTION@
$wanted = @RECORD@ | ConvertFrom-Json
$folder = Join-Path $root $marker
$state = Join-Path $folder 'state.json'
$refreshPath = Join-Path $folder 'refresh.ps1'
$refresh = @REFRESH@
SafeLedger $folder
SafeLedger $state
SafeLedger $refreshPath
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator consent required: open PowerShell with Run as administrator, approve UAC, and rerun the displayed command with --apply. No automatic elevation.'
}
$r = $null
if (Test-Path -LiteralPath $state) {
    $r = Get-Content -Raw -LiteralPath $state | ConvertFrom-Json
    if ($r.marker -ne $marker -or $r.owner -ne $owner -or $r.mode -ne 'windows' -or $r.port -lt 1024 -or $r.port -gt 65535) { throw 'Refused foreign ownership record' }
    if ($r.address -notmatch '^\d+\.\d+\.\d+\.\d+$' -or -not $r.peers -or $r.interface -isnot [string]) { throw 'Invalid ownership record' }
    if ((Test-Path -LiteralPath $refreshPath) -and [IO.File]::ReadAllText($refreshPath) -ne $refresh) { throw 'Refused changed refresh script' }
} elseif (Test-Path -LiteralPath $folder) { throw 'Refused unmarked existing folder' }
$description = 'cdp-setup-kit owned share v1: ' + $owner + ' / ' + $marker
if ($action -eq 'unshare') {
    if (-not $r) {
        if ((Get-NetFirewallRule -Name $marker -ErrorAction SilentlyContinue) -or (Get-NetFirewallRule -Name ($marker + '-deny') -ErrorAction SilentlyContinue) -or (Get-ScheduledTask -TaskName ($marker + '-refresh') -ErrorAction SilentlyContinue)) { throw 'Refused entries without ownership record' }
        Write-Output 'No owned share; unchanged.'
        exit 0
    }
    CheckResources $r $folder $description
    if (Get-ScheduledTask -TaskName ($marker + '-refresh') -ErrorAction SilentlyContinue) {
        # Prevent a boot refresh racing removal; this is only our recorded task.
        Disable-ScheduledTask -TaskName ($marker + '-refresh') | Out-Null
        Stop-ScheduledTask -TaskName ($marker + '-refresh')
        Unregister-ScheduledTask -TaskName ($marker + '-refresh') -Confirm:$false
    }
    if (ProxyValue $r.address $r.port) { Netsh @('interface','portproxy','delete','v4tov4',('listenaddress=' + $r.address),('listenport=' + $r.port),'protocol=tcp') }
    if (Get-NetFirewallRule -Name $marker -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name $marker }
    if (Get-NetFirewallRule -Name ($marker + '-deny') -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name ($marker + '-deny') }
    if (Test-Path -LiteralPath $refreshPath) { Remove-Item -LiteralPath $refreshPath }
    Remove-Item -LiteralPath $state
    # Never recursively remove an unfamiliar file.
    Remove-Item -LiteralPath $folder
    if ($r.root_created -eq $true -and @(Get-ChildItem -LiteralPath $root).Count -eq 0) { Remove-Item -LiteralPath $root }
    Write-Output 'Owned share removed; Chrome remains on loopback.'
    exit 0
}
$ip = @(Get-NetIPAddress -AddressFamily IPv4 -IPAddress $wanted.address -ErrorAction SilentlyContinue)
if ($ip.Count -ne 1) { throw 'Chosen address must be assigned to exactly one local interface' }
$wanted | Add-Member -NotePropertyName interface -NotePropertyValue $ip[0].InterfaceAlias
$wanted | Add-Member -NotePropertyName marker -NotePropertyValue $marker
$wanted | Add-Member -NotePropertyName owner -NotePropertyValue $owner
if ($r) {
    if ($r.address -ne $wanted.address -or $r.port -ne $wanted.port -or $r.interface -ne $wanted.interface -or -not (Matches $r.peers $wanted.peers)) { throw 'Existing share differs; unshare first' }
    CheckResources $r $folder $description
} else {
    CheckProxy $wanted $false
    if ((Get-NetFirewallRule -Name $marker -ErrorAction SilentlyContinue) -or (Get-NetFirewallRule -Name ($marker + '-deny') -ErrorAction SilentlyContinue) -or (Get-ScheduledTask -TaskName ($marker + '-refresh') -ErrorAction SilentlyContinue)) { throw 'Refused existing unowned firewall rule or task' }
}
CheckFirewall $wanted
if ((Get-Service iphlpsvc).Status -ne 'Running') { throw 'IP Helper must already be running; this kit does not change services' }
if ((Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri ('http://@LOOPBACK@:' + $wanted.port + '/json/version')).StatusCode -ne 200) { throw 'Loopback CDP unavailable' }
$wanted | Add-Member -NotePropertyName root_created -NotePropertyValue (-not (Test-Path -LiteralPath $root))
if (-not (Test-Path -LiteralPath $root)) {
    New-Item -ItemType Directory -Path $root | Out-Null
    & icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to protect machine ledger' }
    & icacls.exe $root /setowner '*S-1-5-32-544' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to set machine ledger owner' }
} else {
    # Refuse a machine ledger writable by any identity other than SYSTEM/admin.
    $acl = Get-Acl -LiteralPath $root
    foreach ($ace in $acl.Access) {
        $sid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        $write = [Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
        if ($ace.AccessControlType -eq 'Allow' -and ($ace.FileSystemRights -band $write) -and $sid -notin @('S-1-5-18','S-1-5-32-544')) { throw 'Refused writable machine ledger' }
    }
}
if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder | Out-Null }
# Journal before mutation: partial failures can be inspected and removed by unshare.
if (-not $r) { [IO.File]::WriteAllText($state, ($wanted | ConvertTo-Json -Depth 5)) }
[IO.File]::WriteAllText($refreshPath, $refresh)
if (-not (Get-NetFirewallRule -Name $marker -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $marker -DisplayName $marker -Description $description -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP -LocalPort $wanted.port -LocalAddress $wanted.address -RemoteAddress $wanted.peers -InterfaceAlias $wanted.interface -EdgeTraversalPolicy Block | Out-Null
}
if (-not (Get-NetFirewallRule -Name ($marker + '-deny') -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name ($marker + '-deny') -DisplayName ($marker + '-deny') -Description $description -Direction Inbound -Action Block -Enabled True -Profile Any -Protocol TCP -LocalPort $wanted.port -LocalAddress $wanted.address -RemoteAddress $wanted.denied -InterfaceAlias $wanted.interface | Out-Null
}
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $refreshPath + '"'
if (-not (Get-ScheduledTask -TaskName ($marker + '-refresh') -ErrorAction SilentlyContinue)) {
    $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT30S'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName ($marker + '-refresh') -Description $description -Action $taskAction -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest | Out-Null
}
Netsh @('interface','portproxy','add','v4tov4',('listenaddress=' + $wanted.address),('listenport=' + $wanted.port),'connectaddress=@LOOPBACK@',('connectport=' + $wanted.port),'protocol=tcp')
CheckResources $wanted $folder $description
Write-Output 'Owned share installed/verified. Check allowed and unlisted peers separately.'
'''

STATUS = r'''
@COMMON@
$owner = @OWNER@
$result = @{}
if (Test-Path -LiteralPath $root) {
    foreach ($folder in @(Get-ChildItem -LiteralPath $root -Directory)) {
        SafeLedger $folder.FullName
        $state = Join-Path $folder.FullName 'state.json'
        SafeLedger $state
        if (-not (Test-Path -LiteralPath $state)) { continue }
        $r = Get-Content -Raw -LiteralPath $state | ConvertFrom-Json
        if ($r.owner -ne $owner) { continue }
        $description = 'cdp-setup-kit owned share v1: ' + $owner + ' / ' + $r.marker
        $health = 'installed'
        try {
            CheckResources $r $folder.FullName $description
            CheckFirewall $r
            if (-not (ProxyValue $r.address $r.port) -or -not (Get-NetFirewallRule -Name $r.marker -ErrorAction SilentlyContinue) -or -not (Get-NetFirewallRule -Name ($r.marker + '-deny') -ErrorAction SilentlyContinue) -or -not (Get-ScheduledTask -TaskName ($r.marker + '-refresh') -ErrorAction SilentlyContinue)) { $health = 'partial; rerun share or unshare' }
        } catch { $health = 'drift: ' + $_.Exception.Message }
        $r | Add-Member -NotePropertyName state -NotePropertyValue $health
        $result[$r.marker.Substring('cdp-setup-kit-'.Length)] = $r
    }
}
ConvertTo-Json -InputObject $result -Depth 5 -Compress
'''


def expand(template, values):
    return re.sub(r"@[A-Z]+@", lambda match: values.get(match.group(), match.group()), template)


def _common():
    return expand(COMMON, {'@LOOPBACK@': LOOPBACK})


def script(name, record, owner, action):
    if record:
        record = dict(record)
        remaining = [ipaddress.ip_network((0, 0))]
        for peer in record['peers']:
            single = ipaddress.ip_network(peer + '/32')
            remaining = [part for network in remaining for part in (network.address_exclude(single) if single.subnet_of(network) else [network])]
        record['denied'] = sorted(str(network) for network in remaining)
    refresh = expand(REFRESH, {'@COMMON@': _common(), '@LOOPBACK@': LOOPBACK})
    # One substitution pass keeps arbitrary quoted paths from becoming tokens.
    return expand(MUTATE, {
        '@COMMON@': _common(), '@LOOPBACK@': LOOPBACK,
        '@REFRESH@': quote(refresh), '@MARKER@': quote(APP_NAME + '-' + name),
        '@OWNER@': quote(owner), '@ACTION@': quote(action),
        '@RECORD@': quote(json.dumps(record)),
    })


def status_script(owner):
    return expand(STATUS, {'@COMMON@': _common(), '@OWNER@': quote(owner)})
