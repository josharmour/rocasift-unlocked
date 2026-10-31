from pathlib import Path
import re, json, hashlib, html, collections, bisect, zipfile, os

SRC=Path(os.environ.get('ROCA_UART_SOURCE', str(Path(__file__).resolve().parents[3]/'device/uart')))
OUT=Path(__file__).resolve().parent
ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
STAMP=re.compile(r'\[\d\d:\d\d:\d\d\.\d{3}\] ?')
def lines(b):
    if not b:return []
    a=b.split(b'\n')
    return a[:-1] if a[-1]==b'' else a
def clean(s):
    s=STAMP.sub('',s)
    s=ANSI.sub('',s).replace('\r','').strip()
    return s
def redact(s):
    s=re.sub(r'(systemd\.machine_id=)[^\s]+',r'\1[REDACTED_MACHINE_ID]',s)
    s=re.sub(r'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b','[REDACTED_MAC]',s)
    s=re.sub(r'(/run/docker/netns/)[^\s.]+',r'\1[REDACTED_NAMESPACE]',s)
    s=re.sub(r'(/var/lib/docker/overlay2)[^\s]*?(/merged)',r'\1/[REDACTED_LAYER]\2',s)
    s=re.sub(r'(libcontainer container )[^\s:]+',r'\1[REDACTED_CONTAINER_ID]',s)
    s=re.sub(r'(?i)((?:password|passwd|access_token|refresh_token|authorization|sharedaccesskey|client_secret)\s*[:=]\s*)\S+',r'\1[REDACTED_SECRET]',s)
    return s
def raw_display(b):
    # Escape controls rather than interpreting terminal cursor movements.
    s=redact(STAMP.sub('',b.decode('utf-8','backslashreplace')))
    return ''.join(('\\x%02x'%ord(c)) if ord(c)<32 and c!='\t' else c for c in s)

# Every baseline line has a deliberately assigned interpretation. Ranges apply
# only to the interpretation, never to source-line coverage or original text.
BASE={}
def add(spec, meaning, relevance='Low direct relevance to scan failures or missing images. Retain as a startup baseline; no follow-up is justified by this line alone.', lead='Compare with a failing boot only if this component later reports a fault.', confidence='High for the printed event; no application-level conclusion.'):
    for part in spec.split(','):
        ns=part.split('-'); start=int(ns[0]);end=int(ns[-1])
        for n in range(start,end+1): BASE[n]=(meaning,relevance,lead,confidence)

add('3','Early firmware identifies its silicon/revision and build string. The trailing numbers are vendor fields whose meanings are not established.','Useful firmware fingerprint; not an independently verified chip specification.','Use this exact banner when requesting matching vendor symbols or boot documentation.','High for banner; low for undocumented field meanings.')
add('4','Build timestamp and commit identifier of the early firmware, not the time of this boot.','Helps distinguish firmware builds across captures.','Match the build/commit against an authorized firmware release record.')
add('7,16,18,30','Short vendor boot-stage marker; its expansion is undocumented in the captured evidence.','Provides ordering only; it does not establish an error or an access interface.','A matching firmware source or symbol map is needed to decode this marker.','High that marker was printed; meaning unknown.')
add('8','Early firmware applies an AVS voltage setting; the printed value is 1050, with no unit in this line.','Power initialization context, not a diagnostic shell or a security fuse setting.','Correlate only if power instability is independently observed; do not alter voltage values.')
add('9','AVS-related register, voltage-bin and efuseEscape values are reported.','This is voltage calibration context; efuseEscape does not establish a debug-unlock mechanism.','Obtain the matching vendor register definitions before interpreting individual bits.','High for values; undocumented bit semantics.')
add('10','Introduces AVS efuse calibration values.','These following fuse fields concern voltage calibration; they do not establish JTAG, UART or secure-boot fuse policy.','No configuration change follows from this header.')
add('11','Reports that the AVS efuse calibration is programmed.','No evidence here that debugging interfaces are fuse-disabled.','Use AVS documentation only if diagnosing a power/calibration fault.')
add('12','Reports the lower AVS VDD limit encoding (39).','A coded calibration limit, not proven to be a voltage in volts or millivolts.','Do not convert or change it without vendor definitions.')
add('13','Reports the upper AVS VDD limit encoding (39).','Matches the lower printed encoding in this boot; no scan-failure implication on its own.','Compare calibration fields across boots without modifying them.')
add('14','Reports the target DRO field (65535).','Its physical interpretation and whether this is a sentinel are unknown.','Vendor AVS definitions are needed; do not infer bad hardware from the numeric maximum.','High for value; unknown field semantics.')
add('15','Reports the Vsense0 selection field (0).','Voltage-sensing configuration context only.','No scan diagnostic action follows without vendor definitions.')
add('17','Firmware calls Configure_Flashes and prints an execution address and arguments.','Shows flash initialization exists, not a callable recovery command or a storage-image location.','Identify the function in matching firmware sources if those are legitimately available.','High for call name; argument meanings unknown.')
add('19','DDR initialization reports DDR4, an 800 MHz clock and chip organization/part label.','Memory baseline for diagnosing boot failures; not a claim about free image-buffer capacity.','Compare against later Linux memory accounting; avoid interpreting the two as identical totals.')
add('20','DDR training prints L and H calibration encodings.','Values can vary between boots without demonstrating RAM failure.','Look for explicit training failure or memory errors before attributing scan loss to RAM.','Medium: placement supports training context; proprietary encodings unknown.')
add('21','DDR training prints WL0 calibration words, plausibly write-leveling results.','A hardware calibration baseline; no pass/fail threshold is provided.','Compare matching firmware boots; vendor training documentation is required for thresholds.','Medium for write-leveling expansion; high for printed values.')
add('22','DDR training prints the VD range.','No documented threshold connects this range to scanning failures.','Retain exact range for comparison; vendor definition is missing.','Medium for training context; precise acronym unknown.')
add('23','DDR training prints the VP range.','No direct evidence of a memory fault.','Retain exact range for comparison; vendor definition is missing.','Medium for training context; precise acronym unknown.')
add('24-27','DDR training prints this BL lane/index and two calibrated ranges.','This particular lane can be compared across boots; variability alone is not failure.','Escalate only alongside explicit training/runtime memory errors.','Medium for lane-training interpretation; limits undocumented.')
add('28-29','Firmware reports a successful SHA comparison at this stage.','Evidence of a comparison succeeding; it does not identify every authenticated object or prove storage encryption.','Use matching boot code to establish exactly which object was checked.')
add('31','Firmware hands execution to application processor core 0 at the printed RAM address.','Marks the transition toward U-Boot; the address is not a storage partition or a console endpoint.','Use as a boot-stage boundary.')
add('34','Identifies U-Boot 2022.01 and its build timestamp.','Use version-matched bootloader documentation; this capture does not show an autoboot countdown or USB-keyboard setup.','A saved bootloader configuration is needed to establish input devices; no boot interruption was tested here.')
add('36','U-Boot reports 3 GiB of DRAM in its own accounting.','Linux later reports a 4 GiB physical total; the difference alone does not prove failed RAM.','Compare reservation/bank configuration in matching device tree and bootloader sources.')
add('37','U-Boot selects a board FIT configuration labeled pegmatite-u-boot.','Useful internal platform identifier, not independent physical-board identification.','Use this string to locate matching source/configuration artifacts.')
add('38-40','The SDHCI setup code says the hardware does not specify a base clock frequency.','Boot warning; storage still initializes later. It is not evidence of a failed image upload.','Correlate the controller instance and later I/O errors before treating it as causal.')
add('41','U-Boot enumerates three mv_sdh MMC controller instances.','Distinguishes controller numbers; not three confirmed storage cards.','Cross-reference later mmc1/eMMC discovery and actual partition mounts.')
add('42','U-Boot begins loading its environment from MMC while board-assembly discovery reports an I2C-bus failure.','Two interleaved facts: board-ID lookup fails, while a subsequent OK follows the environment load.','Do not treat the I2C error as proof the environment failed to load.')
add('43','A second board-assembly lookup fails to obtain the I2C bus.','Potential optional-board identification limitation, not proven scan failure.','Inspect matching board-assembly code or vendor diagnostics if model detection is wrong.')
add('44','An OK follows the environment-load sequence.','The immediately preceding I2C warnings do not prevent continuing boot.','Retain the adjacent lines to avoid attributing OK to the wrong operation.')
add('45,47','Panel EEPROM reader cannot obtain its I2C bus.','Display/panel discovery warning; does not locate a serial header.','Check only if the device is expected to have that panel hardware.')
add('46,48','Panel EEPROM probe reports no panel option.','Consistent with an absent optional panel; hardware expectations are needed to call it a fault.','Compare with OEM bill of materials rather than assuming failed hardware.')
add('49','LCD initialization reports no VGA panel.','No proof of a usable physical monitor or boot menu.','Verify the actual display configuration before considering keyboard/display diagnostics.')
add('50','A card voltage-select request times out (-110).','The line does not identify the slot; mmc1 reads and Linux root mount later succeed.','Look for controller-specific runtime I/O errors; do not blame the working eMMC from this line alone.')
add('51','Prints the boot command sequence: primary MMC read, SHA verification, legacy-recovery check, CRAMFS script; then secondary fallback and a final loop.','Describes potential control flow, not proof that every branch executed. Shows firmware scripts are storage-resident.','Compare the subsequent actual read/authentication/script messages; do not execute or edit this command.')
add('52','A lookup for uaa in nvrom fails.','The object and expected presence are undocumented; boot continues.','Matching vendor source is required to interpret uaa; do not equate it with credentials.','High for lookup failure; meaning unknown.')
add('53','Reports VCF status and error registers; error field is zero.','No decoded status-bit meaning is available.','Retain the exact values for vendor interpretation; zero error is not a complete health test.','High for fields; undocumented semantics.')
add('54','U-Boot successfully writes its environment to MMC device 1.','Boot itself changes persistent state. Rebooting is not a strictly read-only evidence-preservation action.','Preserve existing captures before any separately authorized reboot; no write was performed for this report.')
add('55','Switches the MMC hardware partition selection to partition 0 successfully.','This hardware partition selector is distinct from Linux p1–p8 logical partitions.','Keep these numbering systems separate in storage analysis.')
add('56','MMC device 1, hardware partition 0, is selected.','Identifies the source used by the following firmware read.','Cross-reference later Linux mmcblk1 identification without assuming all numbering is interchangeable.')
add('58','Reads the printed block range from MMC device 1 successfully.','Confirms this boot could read that firmware region; not a test of all storage or scan buffers.','Use block counts as boot-layout evidence only; avoid raw storage writes.')
add('59','Boot code reports authentication success.','Applies to this operation; does not establish full secure-boot policy, fuse state or encryption.','Matching verification code is needed to establish trust-chain scope.')
add('60,63,65','CRAMFS loads the indicated byte count into the indicated RAM address.','Reveals packaged boot content and RAM staging, not recoverable scan-image locations.','Follow the next script/FIT message to identify the loaded object.')
add('61,64','U-Boot executes a previously loaded script at the printed RAM address.','Explains the staged boot flow; not an exposed interactive shell.','Inspect an authorized offline copy of that script if available.')
add('62','Boot script chooses root partition 3.','Later dm-verity uses mmcblk1p3; BOOT_PARTITION=5 is a separate boot label.','Use mounted-device evidence to distinguish root, boot and writable data partitions.')
add('66','Begins loading the kernel from a FIT image in RAM.','FIT bundles boot components and metadata; this is not Docker packaging.','Use FIT documentation for offline structure interpretation [S5].')
add('67,81','Selects the named FIT configuration/device-tree variant.','Strong source-search identifier for this firmware, not an independently confirmed board revision.','Match this exact configuration to an authorized firmware/device-tree artifact [S5].')
add('68','Selects kernel-1 from the FIT bundle.','Identifies which bundled kernel subimage is attempted.','Compare to later Linux version to tie packaging to the running kernel [S5].')
add('69','FIT describes the subimage as the Linux kernel.')
add('70','FIT marks this subimage as a kernel image.')
add('71','The kernel payload is gzip-compressed.','Compression is not encryption and does not protect or locate scan images.','An authorized offline FIT copy could be structurally inspected without modifying the device.')
add('72','Reports the kernel payload start address in the loaded FIT buffer.','A RAM address, not an eMMC offset or diagnostic endpoint.','Use only when interpreting the matching in-memory FIT layout.')
add('73','Reports the compressed kernel payload byte count.','Firmware-size baseline; not available image storage.','Compare only against matching firmware packages.')
add('74,88','The FIT subimage architecture is AArch64.','Useful for interpreting binaries or building a diagnostic package; does not confer installation access.','Match any authorized offline tools to ARM64.')
add('75','The FIT operating-system field is Linux.')
add('76','Reports the kernel RAM load address.')
add('77','Reports the kernel execution entry address.')
add('78,89','The FIT subimage hash algorithm is SHA-256.','Integrity metadata, not an encryption algorithm or private key.','Determine verification policy from matching boot code, not this field alone [S5].')
add('79,90','Prints the FIT subimage SHA-256 digest.','Public integrity fingerprint, not a credential; useful for matching an authorized firmware artifact.','Compare the digest with the same packaged subimage, not the full container or disk [S5].')
add('80','Begins loading the flattened device tree (FDT) from FIT.','The FDT describes hardware resources used by Linux.','A matching offline FDT is a useful source for console, storage and reservation configuration [S5].')
add('82','Selects the named FDT subimage.','Exact identifier helps distinguish the selected hardware description.','Use this name when locating authorized device-tree sources.')
add('83','FIT describes this subimage as the flattened device-tree blob.')
add('84','The subimage type is a flat device tree.')
add('85','The device-tree payload is uncompressed.')
add('86','Reports the FDT payload address within the loaded FIT buffer.')
add('87','Reports the FDT payload size (92,832 bytes).','Useful for matching an offline DTB; not image-buffer capacity.','Validate a matching offline artifact by size and digest.')
add('91','U-Boot will boot using the FDT at the printed RAM location.')
add('92','U-Boot decompresses the kernel payload.')
add('93','U-Boot fails to reserve a 0x12c000-byte FDT region at 0x7fec4000.','The same region later appears as LCD VRAM. Boot continues, so this is not proof of fatal memory failure.','Correlate with the later LXK VRAM warning and matching device-tree reservation; do not change it blindly.')
add('94','The FDT is relocated to the printed RAM range successfully.','The earlier reservation warning did not prevent this load.','Retain both messages together when asking the vendor about memory layout.')
add('96','U-Boot transfers control to Linux.','Boot-stage boundary; no interactive bootloader command prompt is shown.','Use later kernel messages for runtime rather than bootloader capability claims.')
add('98','Linux starts on the boot CPU and prints its architectural CPU identifier.','Hardware/software baseline; not a header pinout.','Decode only against authoritative CPU documentation if needed.')
add('99','Identifies Linux 6.12.54-yocto-standard, ARM64 GCC 13.3, binutils and SMP/PREEMPT build options.','The printed 2011 kernel build date conflicts with newer toolchain/firmware dates; it is not reliable boot wall time.','Use the RTC and capture timestamps for chronology; version-match kernel documentation.')
add('100','Linux reports its device-tree machine-model string.','Useful platform fingerprint; no independent confirmation of the exact marketed SoC.','Match vendor device-tree/source identifiers before transferring another model’s findings.')
add('101,162','No UEFI firmware/services are present for this boot.','Consistent with U-Boot startup; not an error requiring UEFI recovery.','No direct scan-debug action follows.')
add('102','Reserves a 152 MiB contiguous-memory allocator (CMA) pool.','Relevant to DMA/image-buffer allocation, but this line reports capacity, not exhaustion or a saved-image file.','If scan allocation fails later, collect allocation errors and memory pressure from an authorized support export.')
add('103','Initializes the shared DMA pool device-tree node.','Shows a pool is configured; no image ownership or retention policy is established.','Match the pool consumer in vendor driver/device-tree sources.')
add('104','Prints the reusable CMA physical address range.','A memory-layout detail for DMA; not persistent storage.','Use only with matching driver allocation evidence.')
add('105','Reserves a tiny non-reusable SMP boot region.','CPU bring-up bookkeeping; no direct scan-image recovery lead.','No follow-up absent CPU startup failures.')
add('106','Reserves a non-reusable region named r4.','A vendor memory region; the label alone does not establish which firmware processor owns it.','Inspect the matching device-tree node and driver before interpreting it.','High for reservation; consumer unknown.')
add('107','LXK VRAM reservation setup ignores a region because it lies outside kernel memory.','Display-memory layout warning related to the earlier FDT reservation, not proof of scan-buffer loss.','Compare this region with FDT and framebuffer configuration.')
add('108','Initializes the vendor lcd_vram memory node.')
add('109','Prints the 1,200 KiB non-reusable LCD VRAM region.','Correlates the reservation warning with display memory.','A matching DTB can explain the discrepancy; no modification is warranted from this alone.')
add('110','Introduces Linux memory allocation zones.')
add('111','Shows the DMA zone address window; it is not a statement that every address in the window contains RAM.')
add('112','No separate DMA32 zone is populated.')
add('113','Shows the Normal zone address window, which can include gaps between physical banks.')
add('114','Introduces movable-zone information; this line alone lists no populated range.')
add('115','Introduces actual early physical-memory node ranges.')
add('116','Reports the lower physical RAM bank (2 GiB).','One of two 2 GiB banks, unlike the much larger address-span window.','Use bank lengths rather than the encompassing address span to calculate RAM.')
add('117','Reports the upper physical RAM bank (2 GiB).','Together with the lower bank explains the Linux 4 GiB total.','Do not count the intervening address gap as RAM.')
add('118','Creates node 0 spanning the listed memory address limits.')
add('119','Allocates per-CPU kernel data areas.')
add('120,169,171,173','Detects a virtually indexed, physically tagged instruction cache on this CPU.')
add('121-123','Detects an ARM CPU erratum for which the kernel has architecture handling.','An erratum identification is not a runtime crash report.','Investigate only with a matching actual failure or vendor erratum applicability.')
add('124,180','Applies kernel alternative instruction sequences for detected CPU capabilities.')
add('125','Kernel arguments route console output to ttyS0 at 115200n8, configure SWIOTLB, pass a redacted machine identity, and create a read-only dm-verity mapping over mmcblk1p3 for root; BOOT_PARTITION is 5.','Strong evidence for console output and root integrity checking, not an interactive login, encryption or image spool location.','Inspect saved unit/configuration files for log sinks and getty presence; obtain the writable-mount map separately [S1,S6].')
add('126','Linux does not consume BOOT_PARTITION=5 and passes it to userspace.','Expected handling for a vendor userspace parameter; not a kernel boot failure.','Find the userspace consumer in authorized offline scripts [S6].')
add('127','Allocates the directory-entry lookup cache hash table.')
add('128','Allocates the inode lookup cache hash table.')
add('129','Builds memory zone lists and reports physical page count.')
add('130','Reports compile/runtime memory initialization policy for stack and heap.','Not evidence of application memory contents or a cause of lost images.','No settings or security change follows from this configuration report.')
add('131','Configures software I/O translation/bounce-buffer areas.')
add('132','Allocates a 64 MiB SWIOTLB bounce-buffer region for DMA.','Relevant only if later DMA mapping exhaustion/errors occur.','Correlate later DMA errors with this pool; do not assume it stores recoverable images.')
add('133','Initializes the SLUB kernel object allocator with alignment/order/CPU/node parameters.')
add('134','Reserves entries for kernel function tracing.','ftrace support exists in this kernel; this does not mean tracing was enabled or retained.','An authorized local support path could inspect available trace configuration; no tracing was enabled here.')
add('135','Completes allocation of the ftrace tables.','This is tracing infrastructure, not a captured call trace.','Check an authorized trace export only if the vendor enables one.')
add('136','Uses the preemptible hierarchical read-copy-update synchronization implementation.')
add('137','Restricts RCU CPU bookkeeping to the four detected CPUs.')
add('138','Enables the trampoline variant of task RCU.')
add('139','Enables the rude variant of task RCU.')
add('140','Enables the tracing variant of task RCU.')
add('141','Reports the RCU scheduler-enlistment delay in jiffies.')
add('142','Adjusts RCU hierarchy fanout for this CPU count.')
add('143','Configures task-RCU callback CPU distribution.')
add('144','Configures rude task-RCU callback CPU distribution.')
add('145','Configures tracing task-RCU callback CPU distribution.')
add('146','Reports initial interrupt-descriptor allocation parameters.')
add('147','Installs the GIC ordinary interrupt handler.')
add('148','Installs the GIC fast interrupt handler.')
add('149','Warns that interrupt 9’s chip did not update the effective affinity mask.','Startup IRQ-affinity warning, not an observed lost camera interrupt.','Identify IRQ 9’s owner in a matching authorized interrupt map before correlating a fault.')
add('150','Sizes sleepable-RCU structures based on contention policy.')
add('151','Initializes a 25 MHz architectural timer.')
add('152','Registers the architectural counter clocksource and its wrap/idle limits.')
add('153','Reports the scheduler clock width, frequency, resolution and wrap interval.')
add('154','Installs a dummy text console before the framebuffer console.','Does not imply an attached monitor or user-input path.','Do not infer a usable boot menu from a console geometry.')
add('155','Computes delay-loop calibration from the timer rather than measuring a loop.','BogoMIPS is not a scan-throughput benchmark.','Use actual job timings for performance analysis.')
add('156','Sets the default process-ID number limit.')
add('157','Allocates the mount cache hash table.')
add('158','Allocates the mountpoint cache hash table.')
add('159','Uses hierarchical sleepable RCU.')
add('160','Reports an SRCU no-delay phase limit.')
add('161','Configures timer-migration hierarchy parameters.')
add('163','Initializes the vendor Pegmatite APMU block; power-management expansion is plausible, not established by this line.','Platform initialization baseline.','Matching vendor source is needed for register-level meaning.','Medium for role; exact implementation unknown.')
add('164','Initializes the vendor Pegmatite AIB block; acronym is not defined in this capture.')
add('165','Initializes the vendor Pegmatite CIU block; acronym is not defined in this capture.')
add('166','Initializes Pegmatite address-extension support.')
add('167','Initializes the Pegmatite interconnect/fabric block.')
add('168','Begins bringing secondary CPU cores online.')
add('170,172,174','The specifically numbered secondary CPU boots successfully and reports its architectural identifier.')
add('175','Reports one memory/CPU node with four online CPUs.')
add('176','Confirms four processors activated.')
add('177','All CPUs entered the kernel at architectural exception level EL1.','EL1 is a CPU privilege level, not a root login or an unlocked console.','No access conclusion follows.')
add('178','Detects support for 32-bit userspace at EL0.')
add('179','Detects CPU CRC32 instruction support.')
add('181','Reports Linux RAM accounting: 4 GiB total, with kernel, reserved and CMA portions deducted from available memory.','Relevant capacity baseline, not live free RAM during scanning.','Compare with authorized runtime memory/allocation diagnostics if scan failures suggest pressure.')
add('182','Initializes the automatic device-node filesystem.')
add('183','Registers the jiffies fallback clocksource.')
add('184','Allocates the futex synchronization hash table.')
add('185','Reports pages eligible for allocations outside the procedure-linkage-table range.')
add('186','Reports pages in the procedure-linkage-table allocation range.')
add('187','Initializes pin-control infrastructure.','No physical header pinout or voltage is disclosed.','Only a verified board schematic can map header connections.')
add('188','No valid DMI table is present.','Common on device-tree ARM systems; not evidence of missing firmware.','Use device-tree/vendor identifiers for hardware matching.')
add('189','Registers kernel netlink/routing communications.','Host configuration IPC, not a newly opened TCP service.','Do not map protocol-family registration to a network port.')
add('190-192','Preallocates the named 512 KiB atomic DMA pool.','DMA capacity baseline; this line is successful allocation, not exhaustion.','Look for runtime DMA errors before relating it to image acquisition.')
add('193','Registers the step_wise thermal governor.')
add('194','Selects the menu CPU-idle governor.')
add('195','Initializes address-space identifier allocation.')
add('196','Selects deflate compression for persistent crash records.','Promising kernel-crash evidence path, not ordinary scanner or Docker logs.','Request existing pstore archives through an authorized support export [S2,S9].')
add('197','Registers ramoops as the pstore backend.','Crash records may survive some resets; RAM retention and configuration determine persistence, not power-loss guarantees.','Check existing archives before rebooting; do not clear them [S2,S9].')
add('198','Configures a 1 MiB ramoops area at physical 0x50000000, with ECC field 0.','Potential kernel crash/oops history; not a disk partition or missing-image store.','An authorized export can inspect /sys/fs/pstore and configured archives; content is not shown here [S2,S9].')
add('199','Initializes the central DMA module.')
add('200-202','Registers this named virtual DMA controller type and its physical/virtual channel counts.','Potential scan-data movement infrastructure, but no consumer or fault is shown.','Map the channel consumer from matching drivers before associating it with scanning.')
add('203','Initializes the SCSI subsystem.','Driver support, not proof a USB storage device is attached.','Use actual device discovery/mount records to establish attached storage.')
add('204-206','Registers the named USB core interface/device driver.','Linux USB support only; this says nothing about U-Boot keyboard input.','Look for actual peripheral enumeration if diagnosing USB devices.')
add('207','Registers Linux media-controller interface support.','Useful capability for video/media drivers, not proof of a V4L camera or its device path.','Identify the actual scanner driver/consumer from saved configuration.')
add('208','Registers Video4Linux capture-interface support.','Could support image acquisition; no camera node, frame or saved image is established.','Obtain authorized device-node and driver mapping before using a camera API.')
add('209','Registers the Linux pulse-per-second timing API.')
add('210','Prints PPS software version and authorship, not a runtime event.')
add('211','Registers precision-time-protocol clock support.')
add('212','Initializes ALSA sound infrastructure.')
add('213','Reports the Bluetooth core version.')
add('214','Registers the Bluetooth protocol family.')
add('215','Initializes Bluetooth HCI device/connection management.')
add('216','Initializes the Bluetooth HCI socket layer.')
add('217','Initializes Bluetooth L2CAP support.')
add('218','Initializes Bluetooth SCO support.')
add('219','Loads VGA arbitration support; no physical VGA display is established.')
add('220','Selects the architectural system counter as the active clocksource.','Relevant to monotonic timing stability, not proof of wall-clock synchronization.','Keep kernel/monotonic and wall-clock timestamps separate.')
add('221','Registers filesystem quota support.')
add('222','Allocates the quota-cache table.')
add('223','Registers IPv4 networking.')
add('224','Allocates the IPv4 identification hash table.')
add('225','Allocates TCP listener lookup capacity.','This count is a hash-table size, not the count of listening ports.','Use actual socket configuration for a service/port map.')
add('226','Allocates the networking perturbation hash table.')
add('227','Allocates the TCP established-connection hash table; it is not the active connection count.')
add('228','Allocates the TCP binding hash table; it does not list bound ports.')
add('229','Summarizes configured TCP hash-table capacities, not live connections.')
add('230','Allocates UDP lookup-table capacity, not an active socket inventory.')
add('231','Allocates UDP-Lite lookup-table capacity.')
add('232','Registers Unix/local sockets.','Allows host IPC, which is relevant to scanner/runtime sockets; it does not expose them to the LAN.','Inspect actual socket units and permissions via an authorized local/support route [S4].')
add('233','Sets the PCI cache-line-size default.')
add('234','Initializes kernel trusted keyrings.','No private key or tenant credential is printed or made accessible.','Do not infer management authorization from kernel key support.')
add('235','Configures working-set tracking metadata for reclaim.')
add('236','Registers SquashFS support.','Later root mount confirms actual use; this registration alone is only capability.','Read the later root-mount event [S11].')
add('237','Registers XFS with security attributes and quotas.','Support does not show that any partition is XFS.','Use mount evidence before claiming a data filesystem type.')
add('238','Registers the 9P filesystem client.','No remote share or endpoint is shown.','A mounted 9P filesystem would require separate evidence.')
add('239','Registers the kernel cryptographic algorithm socket family.')
add('240','Registers asymmetric-key support.')
add('241','Registers an X.509 certificate parser.','Certificate support is not evidence of exported credentials.','No credential extraction is needed for interpreting this line.')
add('242','Loads the SCSI generic block-layer driver.')
add('243','Registers the mq-deadline I/O scheduler.')
add('244','Registers the kyber I/O scheduler.')
add('245','Registers the bfq I/O scheduler.')
add('246','The pinmux driver exposes 244 pins over its register region.','Internal pin-control count, not a physical header pinout.','Do not derive connector assignments or voltage from this number.')
add('247','Warns that a GPIO driver uses deprecated static base numbering.','Developer migration warning, not evidence of an electrical fault.','Only investigate if a related GPIO fails in runtime diagnostics.')
add('248-252','PWM driver rejects the printed c0/c1 combination.','Repeated startup warning; no temporal link to a particular failed card scan is shown.','Compare with successful boots and vendor motor/PWM diagnostics before attributing feed failures.')
add('253','Switches the kernel console to a framebuffer text geometry.','Does not establish an attached display or interactive input.','Use physical/OEM evidence for display capabilities.')
add('254','Loads the 8250/16550-compatible serial driver with four-port capacity.','Capacity is not a map of four exposed headers.','Use actual registered UART lines and verified board evidence.')
add('255','Temporarily disables the legacy ttyS0 printk console during driver handover.','The following enable message shows this is not permanent suppression of UART output.','Keep the disable/enable sequence together.')
add('256','Registers ttyS0 at the printed MMIO/IRQ as an XScale-compatible UART.','Together with console arguments identifies the kernel output route; receive wiring and interactive login are not proved.','Inspect saved getty/unit configuration if available; do not infer header pins.')
add('257','Re-enables the legacy ttyS0 printk console.','Confirms kernel console routing, not container stdout forwarding.','Find container logging configuration separately [S7].')
add('258','Registers a second UART, ttyS1, at a different MMIO/IRQ.','Potential internal interface, but no external header or voltage mapping is established.','Only verified board documentation can locate it physically.')
add('259','Loads the loop block-device driver.')
add('260-262','Ethernet driver cannot find the named optional/special interrupt.','Main Ethernet initialization continues; this is not proof of lost cloud connectivity.','Correlate with link/error counters and upload failures via authorized diagnostics.')
add('263','Ethernet PTP uses the main clock.')
add('264','Reports Ethernet controller user and Synopsys IP revision identifiers; these are not MAC addresses.')
add('265','Identifies the Ethernet IP block as DWMAC1000.')
add('266','Enables a driver workaround for sticky low-power idle.')
add('267','Reports support for the Ethernet DMA capability register.')
add('268','Reports receive checksum-offload capability.')
add('269','Reports checksum-offload engine type 2.')
add('270','Reports transmit checksum-insertion capability.')
add('271','Reports wake-on-LAN capability; it does not say WOL is enabled or authorized remotely.')
add('272','Selects normal Ethernet DMA descriptors.')
add('273','Selects ring-mode Ethernet descriptors.')
add('274','Enables receive interrupt mitigation using the Ethernet hardware watchdog timer; distinct from system-reset watchdog.')
add('275','A hardware-monitor temperature input is not attached to a thermal zone.','Telemetry integration warning; not proof of overheating.','Correlate real temperature/time/error data before diagnosing thermal scan failures.')
add('276-282','Registers this named USB network driver.','Driver availability does not mean a matching USB Ethernet adapter is connected.','Use actual peripheral enumeration before inferring alternate network access.')
add('283,295','Initializes this EHCI USB host controller.','Linux host-mode support, not U-Boot keyboard support or a USB container installer.','Use actual peripheral enumeration and supported OEM workflows.')
add('284,296','Assigns the printed USB bus number to this EHCI controller.')
add('285,297','Reports this USB host controller’s IRQ and MMIO region.')
add('286,298','Starts the USB 2.0 EHCI host controller.')
add('287,299','Enumerates the Linux root hub (vendor 1d6b, product 0002).','This is the host’s own root hub, not an attached keyboard or flash drive.','Look for additional downstream device records for real peripherals.')
add('288,300','Reports string-descriptor indexes for the USB root hub.')
add('289,301','The USB root-hub product string identifies the EHCI host controller.')
add('290,302','The root-hub manufacturer string embeds the running Linux/driver version.')
add('291,303','The root-hub serial string is a controller/MMIO identifier, not the sifter’s private serial number.')
add('292,304','Registers the root USB hub.')
add('293,305','Reports one port on this root hub; physical external accessibility is not established.')
add('294,306','Confirms the EHCI controller is operating in host mode; its pointer is already obscured by the kernel.','A USB host exists after Linux starts; no bootloader input or sideload route is proved.','Do not transfer Linux USB capabilities backward to U-Boot.')
add('307','Registers the USB EHSET test driver.','Registration does not mean an electrical test was run or should be invoked.','No action needed.')
add('308','Registers the hardware real-time clock as rtc0.')
add('309','Sets system wall time from the RTC to the printed UTC date/time.','Useful boot chronology anchor, subject to RTC correctness; distinct from host receipt time.','Cross-check a trusted wall clock before correlating cloud events.')
add('310','Provides userspace I2C device interfaces.','Capability only; not authorization to access or alter hardware registers.','Use existing driver logs rather than raw I2C operations.')
add('311','Thermal-sensor registration fails with -19 (ENODEV in Linux errno).','Thermal-framework integration failed; a subsequent internal-temperature reading still prints.','Vendor driver/configuration can explain this distinction; no overheating is established.')
add('312','Prints an internal-temperature reading; units are not stated in this line.','Can be compared across captures, but is not a sustained-load thermal history.','Confirm units and sensor calibration before using a threshold.')
add('313','The watchdog driver supplies an out-of-range timeout value (4294967295).','Likely initialization/default handling, followed by usable timeouts; not proof a reset occurred.','Compare the next driver and systemd watchdog settings.')
add('314','Watchdog driver chooses an initial 10-second timeout.','Later systemd reports 20 seconds; these are sequential configuration stages.','Request reset-cause and watchdog logs if unexplained resets are the symptom.')
add('315','Initializes the device-mapper control interface.','Prerequisite for the root integrity mapping, not proof of encryption.','Use the actual dm-verity table for its role [S1].')
add('316','Registers SDHCI storage-controller support.')
add('317','Prints SDHCI driver attribution; no runtime diagnostic result.')
add('318','Registers the SDHCI platform/device-tree helper.')
add('319,321,332','This SDHCI instance lacks a conf-sdio3 register definition and disables SDR50/DDR50 modes.','A mode limitation, not proof all storage is broken.','Identify the controller/device before correlating throughput or I/O errors.')
add('320,322,333','Driver suggests updating the device tree for the preceding missing configuration.','Generic driver guidance, not a validated firmware modification for this OEM device.','Ask the vendor about the matching DTB; do not change firmware from this message alone.')
add('323','This SDHCI instance obtains a card-detect GPIO.')
add('324-325','Registers Linux USB HID support.','Linux can support HID devices; this does not prove U-Boot can accept a USB keyboard.','A saved bootloader stdin/USB configuration is still needed for boot-interruption feasibility.')
add('326','Linux AVS driver reports its initial encoded value (39).','Relates to early voltage calibration; not a user-facing debug level.','Do not alter power calibration to investigate logs.')
add('327','Registers the Pegmatite mailbox hardware revision.','Interprocessor/vendor IPC infrastructure, not a TCP service.','Use matching mailbox driver sources to identify its consumers.')
add('328','Reports mailbox IRQ and send/ack bit masks.','Hardware signaling details, not network ports or commands to transmit.','No raw register access follows from this report.')
add('329-330','Registers the printed mailbox protocol port number.','These are hardware/mailbox channel identifiers, not TCP ports 1 or 2.','Keep mailbox channels separate from MDCIF TCP 50800.')
add('331','Registers USB audio support; not proof of an attached USB audio device.')
add('334','Initializes XFRM networking configuration over netlink.')
add('335,338,343','Registers the named SDHCI controller as this MMC index using ADMA.','Distinguishes controller identity from later card/partition identity.','Map mmc1 to the successful eMMC discovery; do not conflate mmc0 failure.')
add('336','Registers IPv6 networking.')
add('337','Enables IPv6 segment-routing support.')
add('339','Enables IPv6 in-situ OAM support.')
add('340','Registers packet sockets.')
add('341','Registers bridge firewall integration.','Capability does not show actual filter rules or port reachability.','Existing authorized firewall configuration is needed for reachability explanations.')
add('342','Registers the network transport layer for 9P.','No active 9P server/share is established.','No new endpoint to probe is identified.')
add('344','Registers task statistics support.')
add('345','Loads compiled-in X.509 certificates into kernel trust infrastructure.','No private keys or operator credentials are exposed.','Do not infer cloud tenant access from this.')
add('346-347','Registers a filesystem-encryption-related key type.','This is capability, not evidence any mounted filesystem is encrypted.','Actual mount/policy metadata would be needed to establish encryption.')
add('348','Enables the discovered mmc1 card’s cache.','Storage operation baseline; does not prove every application write was durable.','Upload/image durability requires application acknowledgement and storage policy evidence.')
add('349','Discovers a high-speed MMC card on mmc1.')
add('350','Identifies the mmcblk1 eMMC device and reports 14.5 GiB usable capacity.','Concrete local persistent-storage hardware; no file retention or spool path is shown.','Request a read-only mount/usage inventory through a supported local or vendor export.')
add('351','SPI controller falls back from DMA to programmed I/O.','A transport-mode fallback, not necessarily a failed peripheral.','Identify the SPI consumer before attributing scan delays to this.')
add('352','Configures the Wi-Fi reset regulator’s GPIO as active-low.','No reset action or external pin mapping is established.','Do not manipulate GPIOs based on this line.')
add('353','Configures the Bluetooth reset regulator’s GPIO as active-low.')
add('354','Discovers eight logical partitions on mmcblk1.','Useful storage-layout inventory; only the root mapping is resolved by the boot arguments.','Obtain partition labels/mounts without writing storage; do not guess which contains images.')
add('355','Configures an active-low GPIO for the slb9670 device node.','Name is consistent with a TPM-family part, but this line does not expose keys or prove its security state.','Correlate with the TPM driver/service evidence; no credential extraction is needed.','High for node; hardware identity inferred from name.')
add('356','Reports the 8 MiB eMMC hardware boot0 region.','Distinct from Linux logical partitions and ordinary image storage.','Do not target boot regions for image recovery or write operations.')
add('357,363,365','This I2C controller lacks pinmux recovery information and prints diagnostic values.','Recovery-configuration warning; the unusual numeric field has no established meaning here.','Use matching driver source and actual bus-error evidence; do not infer a secret/address exploit.')
add('358','Reports the 8 MiB eMMC hardware boot1 region.')
add('359','Reports the 4 MiB eMMC replay-protected memory block (RPMB) character interface.','Special protected storage, not an ordinary missing-image directory.','No read/write or key operation is proposed.')
add('360','mmc0 fails to initialize a non-removable card.','mmc1, the eMMC used for root, succeeds; this is not evidence that the root storage failed.','Identify what the OEM expects on mmc0 before treating it as a defect.')
add('361','An I2C abort operation times out.','A real startup bus warning, but the owner and connection to scanning are not established.','Correlate with device-specific failures and matching driver context.')
add('362,364,366','Registers this numbered PXA I2C adapter.','Bus enumeration, not proof every attached peripheral responds.','Use existing device-specific diagnostics if a peripheral is suspect.')
add('367','Registers the vendor LPP console device /dev/ttyLPP0.','A software console device exists; no physical header, interactive shell or UART voltage is established.','Matching vendor driver/unit configuration is the next read-only evidence source.')
add('368','Registers a platform button input device.','Explains button monitoring later; no reset sequence or action is shown.','Use OEM documentation for button behavior, not inferred key presses.')
add('369','Device-mapper waits for underlying devices before creating configured mappings.')
add('370','Initializes the CPU-idle mailbox integration.')
add('371','dm-verity uses SHA-256 with the sha256-ce implementation.','Integrity checking of blocks, not decryption [S1].','Inspect verification errors if root corruption is suspected; none appears on this line.')
add('372','The dm-0 mapping named verity-p3 is ready.','Confirms creation of the configured integrity-protected root device.','Separate this root mapping from writable data mounts [S1].')
add('373','Disables clocks not claimed by active drivers.')
add('374','Introduces the detected ALSA device list.')
add('375','Lists a loopback audio card.','Software loopback is not proof of physical audio input/output.','No scan-image relevance.')
add('376','Mounts the root filesystem as read-only SquashFS on device 253:0 (dm-0).','Root is compressed/read-only; writable data/logs must use other mounts if persisted. This is not proof of encryption.','Follow /var and Docker mounts; request actual mount/retention configuration [S1,S11].')
add('377','Mounts devtmpfs for kernel-managed device nodes.')
add('378','Releases memory used only during kernel initialization.','Normal cleanup, not deletion of scan images.','No action needed.')
add('379','Executes /sbin/init as the first userspace process.','Boundary between kernel initialization and systemd-managed services.','Use service-specific logs for later application failures.')
add('380','systemd 255 starts as PID 1 and lists compiled feature support, including unified cgroups.','Plus/minus feature flags are build capabilities, not a complete security audit or enabled-service inventory.','Version-match unit semantics; do not infer unrestricted access from missing optional features.')
add('381','systemd identifies the running architecture as arm64.')
add('383','Userspace identifies as Lexmark Poky / Yocto 5.0.7 scarthgap.','Concrete OS-family evidence, more precise than the umbrella Optra product name.','Use this release family for matching packaging and support documentation.')
add('385','No hostname is configured, so systemd chooses its default.','Hostname selection does not establish service binding or network reachability.','Read actual socket configuration for loopback/LAN binding.')
add('386','Sets the hostname to localhost.','This does not mean every server binds to 127.0.0.1.','Do not use hostname as evidence that 50800 is loopback-only.')
add('387','Installs a transient machine-id file.','Runtime identity setup, not proof of cloud enrollment removal or a factory-reset effect.','Keep OS machine identity distinct from Azure/device credentials.')
add('388','systemd opens the hardware watchdog at /dev/watchdog0.','Potential reset-cause context; no watchdog expiration is reported.','Request watchdog/reset-cause history if unexpected reboot is the symptom.')
add('389','systemd reports a 20-second hardware watchdog timeout.','Supersedes the driver’s initial 10 seconds at this later stage.','Do not disable/change the watchdog; compare with actual reset evidence.')
add('390','systemd ignores an unrecognized ConditionPathContains key in powerdown-sound.service.','Unit-file compatibility issue affecting a condition; not proof the service fails or explains a scan fault.','Read the saved unit to determine the intended condition before proposing a correction.')
add('391','Normalizes the IoT Edge management socket path from /var/run/iotedge/mgmt.sock to /run/iotedge/mgmt.sock.','Concrete local Unix management endpoint; no remote TCP API, permissions or invocation authorization is established.','Inspect the unit and supported API access model through an authorized local export [S4,S8].')
add('392','Normalizes the IoT Edge workload socket path to /run/iotedge/workload.sock.','Workload identity services are distinct from cloud management/deployment privileges.','Use supported module authorization documentation; do not replay device credentials [S4,S8].')
add('393','systemd warns that membroker.service uses the special nobody account.','Configuration-hardening warning, not proof of an accessible privilege-escalation or unauthenticated API.','Inspect the service/socket permissions and purpose via authorized saved files.')
add('394','systemd ignores RequiredBy in the wrong section of box-line-reset.service.','A unit metadata error; the line does not establish that a reset occurred.','Read the exact unit and intended dependency before interpreting its effect.')
add('395','Queues the default Multi-User System startup target.','A dependency goal, not proof all services are already healthy.','Follow later started/failed messages and actual application evidence.')

# Unit descriptions are evidence of intended roles. They are not substitutes for
# executable paths, service definitions, socket permissions, or API protocols.
UNITS=[]
def unit(pattern, role, relevance, lead): UNITS.append((re.compile(pattern,re.I),role,relevance,lead))
unit('Flush Journal|Journal Service|Journal Socket','the system journal log collector/transport','Direct log-access lead. Startup/flush success does not establish retention, persistent files, forwarding, or container coverage.','Read existing journal configuration and support exports; /var/log/journal and /run/log/journal are standard possibilities, not confirmed locations here [S3].')
unit('Platform Persistent Storage Archival|pstore crash','the platform crash-record archival/logging path','Strong lead for prior kernel crashes; these services may archive and clear pstore records. They do not recover ordinary scan images.','Request existing /sys/fs/pstore, configured archives, and journal/syslog records via authorized support access [S2,S9].')
unit('System Logging Service|Syslog Socket','the system syslog log collector/transport','A separate host logging path exists alongside journald. Destination files and retention are not printed.','Inspect the saved syslog configuration or vendor log export; do not assume UART receives every syslog message.')
unit('lbtrace','vendor LBTRACE tracing configuration','Potential source of vendor scanner/internal traces; this line does not reveal trace levels, buffer location or relation to SettingsDebugLevel.','Find the saved lbtrace unit, configuration and driver documentation before changing any level.')
unit('LxkScanDataRemote','the LxkScanDataRemote scanner-data server socket','Concrete scanner IPC lead, but name alone does not give protocol, path, TCP port or image retention.','Request the socket unit ListenStream/ListenDatagram and service ExecStart from an authorized export; do not send guessed payloads [S4].')
unit('ScanEngine RPC|ScanEngine and RPC','the ScanEngine RPC service/socket','Likely scanner-control IPC by its label; no safe request format or port mapping is established.','Inspect the matching unit/client source for transport and documented read-only methods [S4].')
unit('membroker|Memory Broker','the memory-broker service/socket','Potential shared image-buffer coordination; its name does not establish persistent storage or a recovery API.','Inspect its unit, permissions and matching client code; do not infer a network port [S4].')
unit('Memory Tuning','a vendor memory-tuning service','Relevant to allocation/performance only with runtime failures; no tuning values are printed.','Read its saved unit/configuration if memory pressure is implicated.')
unit('MDC Interface','the vendor MDC service','The later MDCIF banner explicitly associates this service sequence with TCP 50800; framing, binding and permissions remain unknown.','Use saved service configuration and client code to identify the protocol; no unknown control bytes should be transmitted.')
unit('Docker.*Socket','the Docker daemon API socket','A legitimate local runtime interface exists; listening does not establish access permission, LAN exposure or logging driver.','Inspect the saved socket unit and logging settings through an authorized host/support route [S4,S7].')
unit('Docker Application','the Docker container engine','Confirms a container runtime layer. A started daemon does not mean every skill is healthy or that container stdout reaches UART.','Obtain per-container log driver, mount inventory, exit/restart status and existing logs via authorized support access [S7].')
unit('containerd','the containerd runtime beneath container management','Runtime startup/shutdown boundary, not scanner skill readiness.','Correlate runtime/service logs with a specific failure time, not generic startup success.')
unit('libcontainer container','a container instance managed through the runtime','Confirms an instance starts, but the abbreviated/redacted ID gives no application name or health.','Use an authorized container inventory to map the instance to the scanning application and its log sink.')
unit('Pre-populate container images','local container-image population','Firmware has an image-seeding step; this is not proof of a USB sideload route or custom-image authorization.','Read the saved population unit/script to identify supported source and lifecycle.')
unit('docker-seed','a sifter-specific docker-seed partition expansion step','Reveals storage provisioning for containers. The ellipsized description omits exact partition and command; no card-image spool is established.','Inspect this unit/script and the read-only mount map; do not rerun a resizing action.')
unit('Azure IoT Edge daemon management','the local IoT Edge management socket','Local runtime management is distinct from permission to modify the operator’s cloud deployment.','The earlier unit warning gives /run/iotedge/mgmt.sock; permissions and API access need actual unit/configuration evidence [S4,S8].')
unit('Azure IoT Edge daemon workload','the local IoT Edge workload socket','Workload identity/certificate operations are not a general cloud-tenant management grant.','The earlier warning gives /run/iotedge/workload.sock; inspect documented authorization, not credentials [S4,S8].')
unit('Azure IoT Certificates','the Azure IoT certificate service/API','Identity infrastructure, not a diagnostic log export.','Use supported service diagnostics; do not extract or replay certificates/keys [S8].')
unit('Azure IoT Identity','the Azure IoT identity service/API','Device/module identity exists but does not establish portal or deployment rights.','Separate local diagnostics from operator-managed enrollment [S8].')
unit('Azure IoT Keys','the Azure IoT key service/API','Key operations infrastructure, not an invitation to retrieve key material.','Request service health/logs through supported diagnostics without exposing secrets [S8].')
unit('Azure IoT TPM','the Azure IoT TPM service/API','TPM-backed identity integration; startup alone does not prove every TPM operation succeeds.','Correlate with the earlier TPM self-test warning and supported health diagnostics [S8].')
unit('Azure IoT Edge daemon','the Azure IoT Edge runtime manager','Confirms the runtime lifecycle is present; no successful cloud connection or deployment authorization is shown.','Obtain existing edgeAgent/edgeHub and application logs via authorized support access [S8].')
unit('TPM2 Access Broker','the TPM2 access broker/resource manager','A local TPM coordination service; separate from a cloud login or data recovery route.','Review health logs if identity provisioning fails; do not perform key operations.')
unit('D-Bus proxy for container','a D-Bus proxy described as filtering to com.optra.DeviceUI only','Evidence of a deliberately limited container-to-device UI interface, not a generic network/localhost proxy.','Inspect the proxy policy and supported UI API; this does not prove WebBrowserURL fetch behavior.')
unit('Optra Edge Device UI','the vendor device-UI service','Plausible consumer area for browser/UI settings, but no call site or setting behavior is proven.','Read its saved unit/client interfaces before interpreting WebBrowser or WebBrowserURL.')
unit('Edge Device Web Services','the EWS service or its explicitly named Unix socket','Known local management/UI layer; this log does not enumerate HTTP routes or grant access to internal sockets.','Use established authorized read-only EWS routes and saved frontend/source evidence; avoid localhost proxy assumptions.')
unit('Edge Settings Network Online','the vendor settings hook for network-online state','Shows settings have a network lifecycle hook, not which keys it consumes.','Inspect the saved service/script and key schema; no debug-level behavior is proven.')
unit('Edge Settings Init','vendor settings initialization','Concrete settings lifecycle stage; it does not enumerate values or their consumers.','Read saved initialization code and narrowly selected non-secret keys.')
unit('Edge Settings Monitor','the vendor settings monitor','A process watches settings; this is not evidence that a chosen value affects MDCIF or Docker logging.','Locate consumer call sites and supported log destinations; compare debug levels only with a controlled, separately authorized baseline.')
unit('Verify settings group','reservation/checking of a settings group on /var','Indicates settings-related writable state under /var; does not reveal file paths, credentials or a reset capability.','Read the saved unit/script and configuration layout without dumping sensitive values.')
unit('Edge Manager','a vendor Edge Manager service','A device lifecycle/management component by name; exact operations are not shown.','Inspect its unit and existing logs to map responsibilities to scan/upload failures.')
unit('Edge IoT','a vendor Edge IoT service','Potential cloud integration component by name, not evidence of an acknowledged image upload.','Correlate its existing logs with scan ID, time, retries and server acknowledgements.')
unit('Edge Watchdog','the vendor watchdog setup/service','Finished may describe a one-shot unit; it does not mean the hardware watchdog is disabled.','Read its Type/ExecStart and reset-cause logs before interpreting watchdog behavior.')
unit('Do box line reset','a conditional box-line-reset operation labeled “if /var/blurb exists”','Unit completion does not prove the condition held or that a factory reset occurred; reset semantics are not shown.','Read the exact saved script and condition before recommending any reset.')
unit('Reset boot counts','boot-attempt counter bookkeeping','May mark successful boot progress; does not establish reset-cause history or debugging unlock.','Inspect its saved script if boot fallback behavior matters; do not rerun it.')
unit('Resize Data Partition','a writable data-partition resize operation','Shows boot can perform storage writes; the line does not identify recovered/missing images.','Inspect layout and mount metadata; do not rerun resizing during recovery.')
unit('Auto Config.*extended storage','automatic extended-storage configuration/mounting','Support for some extended storage exists; no attached medium, filesystem or USB-container installer is established.','Read the unit/script and actual mount records to determine supported media behavior.')
unit('Removable Media','a tmpfs-backed removable-media staging mount','The staging directory is volatile; its existence does not mean USB drives install skills.','Inspect supported media handlers and mount records; no USB action was performed.')
unit('Bind mount volatile /srv','a volatile bind mount for /srv','Files placed there may be transient; no scan-image use is shown.','Confirm the backing mount and application path before assuming recoverability after reboot.')
unit('compressed swap.*zram','compressed RAM-backed swap configuration','Memory-pressure support, not persistent disk storage for recoverable images.','Use existing memory/OOM diagnostics if scans fail under load; do not change swap settings.')
unit('SWUpdate|swupdate progress','the software-update service/socket or its progress monitor','Update infrastructure is present; no supported custom-skill USB install route or accepted package policy is shown.','Read OEM update documentation and saved service configuration; do not submit packages.')
unit('USB special mode','a vendor USB special-mode initializer','Exact mode and trigger are unknown; no recovery or sideload behavior is established.','Inspect the initializer’s saved script and OEM guide before considering any USB workflow.')
unit('Button Monitor','the vendor physical-button monitor','Potential local control mechanism, but no press sequence or reset semantics are disclosed.','Use OEM button documentation; no button action is proposed.')
unit('Network Time Synchronization','network time synchronization','Service startup is not proof a time source was reached or synchronized.','Check an authorized synchronization-status record when correlating cloud timestamps.')
unit('Network Name Resolution','the DNS/name-resolution service','Relevant to cloud-upload reachability only if query failures are observed.','Correlate existing DNS failures and upload retries at the same time.')
unit('Wait for Network','a network-configuration readiness wait','Completion is not proof Internet, Azure or upload acknowledgement is working.','Use a known application transaction or existing connection/error logs for end-to-end status.')
unit('Network Configuration','the network configuration service','A configured interface does not prove cloud delivery.','Read existing link/address/route/error diagnostics without changing settings.')
unit('Network Service Netlink','network configuration over local netlink IPC','Not a TCP port or a remote API.','No probe is justified by this socket label.')
unit('IPv[46] Packet Filtering','the packet-filtering framework setup','Service status does not show actual rules; a refusal does not establish loopback-only binding.','Read existing rules/socket binding evidence through an authorized local export.')
unit('Wifi Host AP','vendor Wi-Fi access-point management','A manager starts; this does not prove an AP is currently enabled or reveal its credentials.','Use documented local setup status; do not change enrollment or Wi-Fi settings.')
unit('Wifi-switch','Wi-Fi power-enable setup','Power initialization, not association or Internet connectivity.','Correlate with interface/link evidence if connectivity is failing.')
unit('WPA supplicant','Wi-Fi authentication/association management','Daemon startup alone is not successful association.','Use existing association/error logs without exposing secrets.')
unit('Wireless Heartbeat','a vendor wireless-health monitor','Exact heartbeat protocol and destination are unknown.','Read saved unit/configuration rather than inventing packets.')
unit('Modem Manager','the modem-management daemon','No modem is proven present just because the manager starts.','Ignore unless an actual modem is part of the device’s connectivity.')
unit('Hostname','hostname setup/management','A hostname is not a service binding address.','Use actual ListenStream/bind configuration to determine loopback exposure.')
unit('D-Bus System Message Bus','local D-Bus IPC','A local inter-service bus, not an open remote management channel.','Use documented interfaces and existing policy; do not infer unrestricted invocation.')
unit('Permit User Sessions|User Login Management','local user-session management','No actual user, SSH server, serial getty or usable login is established.','An interactive console requires separate getty/authentication and wiring evidence.')
unit('Password Requests','systemd password-request notification/watch handling','Generic boot infrastructure, not an exposed password or login prompt.','No credential action or access conclusion follows.')
unit('Virtual Console','virtual-console configuration','Does not establish a physical display, keyboard or serial login.','Inspect actual terminal/getty configuration only if an authorized local interface is needed.')
unit('Kernel Debug File System','debugfs mounting','Kernel diagnostic infrastructure exists; mount alone does not expose it remotely or enable a particular trace.','Use a supported local export to inspect relevant read-only diagnostics; no debugfs writes.')
unit('Kernel Trace File System','tracefs mounting','Kernel tracing infrastructure exists, but no active trace or log buffer is shown.','Request existing traces/configuration through authorized support; no tracing was enabled here.')
unit('Kernel Configuration File System','configfs mounting','Configuration infrastructure, not a ready-made debug shell or USB installer.','No writes or configuration changes are justified by this line.')
unit('POSIX Message Queue','POSIX message-queue filesystem mounting','Local IPC infrastructure, not a durable image queue by itself.','Identify actual application consumers before relating it to image buffering.')
unit('Temporary Directory|Daily Cleanup','temporary-directory setup/cleanup scheduling','Potentially transient storage; no application image path is shown.','Confirm the application’s path and cleanup policy before attributing missing images to cleanup.')
unit('Root and Kernel File Systems','root/kernel filesystem mount-policy setup','Does not override the earlier evidence of a read-only SquashFS root; per-mount settings need actual configuration.','Inspect saved mount definitions for writable /var and container storage.')
unit('Load Kernel Module configfs','configfs kernel support','Capability only; no USB configuration was performed by the analyst.','No direct scan failure lead.')
unit('Load Kernel Module drm','DRM display infrastructure','Capability only; no physical display/input path is established.','No direct scan failure lead.')
unit('Load Kernel Module fuse','FUSE userspace-filesystem support','Repeated unit messages do not prove multiple FUSE filesystems or failures.','Actual mounted filesystem records are needed for storage mapping.')
unit('Load Kernel Modules','configured kernel-module loading','Individual driver warnings must be evaluated separately; completion is not a full hardware health test.','Correlate named modules with actual runtime errors.')
unit('Coldplug|Rule-based Manager|udev','udev device discovery/event handling','Boot device enumeration, not proof every peripheral is healthy.','Use named device events for hardware correlation.')
unit('Create.*Static Device Nodes|Create List of Static','static device-node preparation','Creates interface nodes, not proof of device functionality or access permission.','Read actual driver/node permissions only when needed for a supported diagnostic.')
unit('Create System Files','system directory/file initialization','No scan-image creation is implied by this generic setup operation.','Inspect application-specific paths rather than inferring them from this unit.')
unit('Generate network units','network-unit generation from kernel arguments','No actual network arguments or live addresses are shown here.','Inspect generated units from an existing authorized export if network behavior is unclear.')
unit('Apply Kernel Variables','configured kernel sysctl application','This line does not list the variables or imply they caused scan failures.','Read saved sysctl configuration only if a specific networking/memory symptom warrants it.')
unit('Load/Save OS Random Seed','random-number seed persistence','Security initialization, not a user password or image-storage operation.','Do not inspect or publish random seed contents.')
unit('Record.*UTMP','boot/shutdown/runlevel accounting','Useful lifecycle history, not a scanning/upload event log.','Use alongside timestamps to distinguish planned shutdown from a crash.')
unit('Sound|Optra Power','audio-state or startup/shutdown sound handling','Low direct relevance to scan failures; shutdown sound helps identify orderly poweroff context.','No action unless audio behavior itself is the symptom.')
unit('System Power Off','system poweroff completion','Lifecycle evidence; no reset or poweroff was initiated for this report.','Interpret subsequent socket closures/unmounts as part of this recorded shutdown.')
unit('User Database Manager','local user-record lookup IPC','Not proof of a usable account or remote login.','No authentication action follows.')
unit('initctl','a legacy init-control compatibility FIFO','Local compatibility infrastructure, not a network API.','Do not send control commands; no diagnostic information is obtained from its mere existence.')

def state_explanation(state):
    if state in ('Starting','Mounting','Unmounting','Stopping'):return 'The manager announces the operation is beginning; this line alone does not confirm completion.'
    if state in ('Started','Listening on','Mounted'):return 'The manager reports this state reached; it is not an end-to-end application health check.'
    if state=='Finished':return 'The manager reports the startup/one-shot task completed; the description does not disclose all internal actions.'
    if state in ('Stopped','Closed','Unmounted'):return 'Recorded orderly-shutdown context: the manager reports this component released or stopped; do not label it a spontaneous crash.'
    return 'This is a systemd lifecycle record.'

def annotation(stage,meaning,rel,lead,conf='High for the observed event; purpose inferred where only a unit label is available.',level='routine'):
    return dict(stage=stage,meaning=meaning,relevance=rel,verification=lead,confidence=conf,classification=level)

canon=lines((SRC/'boot-full-jrip1-pin2.log').read_bytes())
exact={};numeric={}
LEAD_LINES={34,51,54,62,99,100,102,125,134,135,196,197,198,207,208,232,256,257,258,309,350,354,367,371,372,376,380,383,387,388,389,391,392,393,394}
def norm(s):
    s=re.sub(r'0x[0-9a-fA-F]+|\b[0-9a-f]{24,}\b','HEX',s)
    s=re.sub(r'\b\d+(?:\.\d+)*\b','N',s)
    return s
for i,b in enumerate(canon,1):
    s=clean(b.decode('utf8','replace'))
    if i in BASE:
        stage='Early firmware' if i<34 else 'U-Boot / FIT' if i<98 else 'Linux kernel' if i<380 else 'Userspace / systemd'
        level='warning/error' if re.search(r'error|failed|warning|cannot|not safe|Unknown key|not found|did not|Bad values|timeout.*out of range',s,re.I) else 'routine'
        if level=='routine' and i in LEAD_LINES:level='diagnostic lead'
        v=annotation(stage,*BASE[i],level=level);v['baseline_line']=i
        exact[s]=v;numeric.setdefault(norm(s),v)

def interpret(s, source='', line_no=0):
    s=clean(s)
    if not s or s in ('\x00','\x00\x00\x00','\ufffd','\x00\ufffd'):
        return annotation('Capture formatting','Blank/CR-only line, non-printing NUL, or undecodable startup byte(s); no semantic boot message is established.','No direct diagnostic content. It is retained to preserve exact source-line accounting.','None; use the escaped source to distinguish whitespace from undecodable bytes, without assigning invented meaning.','High for capture content; no semantic interpretation.','formatting')
    if re.fullmatch(r'\d\d:\d\d:\d\d\.\d+ 00',s):
        return annotation('Serial test artifact','Timestamped test record containing a single NUL byte.','No readable target response or boot event is established.','Keep this test artifact separate from the actual boot sequence.','High','test/noise')
    if 'rtc-pegmatite' in s and 'setting system clock' in s:
        return annotation('Linux kernel',*BASE[309])
    if s in exact:return dict(exact[s])
    if norm(s) in numeric:
        v=dict(numeric[norm(s)]);v['variant_note']='Same message structure as baseline; use this line’s printed values, not the baseline values.';return v
    if 'PING-' in s:
        return annotation('Serial test artifact','Repeated PING test text/echo with visible control notation. This is not a firmware boot message.','Explains the very large test file; it does not establish a target shell or successful command execution.','Keep separate from actual boot captures. No device action is needed.','High for test content; echo path not established here.','test/noise')
    if s in ('0m...','[0m...') or re.fullmatch(r'[\[;\d?]*[mHJK]?[. ]*',s):
        return annotation('Capture formatting','Residual terminal/ANSI formatting fragment, possibly split by interleaved output.','Not a standalone error or command; neighboring lines supply the meaningful context.','Use the reconstructed byte stream for the timestamped capture.','High','formatting')
    if 'MDCIF:' in s:
        if 'Listening for TCP connection on port' in s:
            return annotation('MDC / scanner interface','MDCIF reports a TCP listener on the explicitly printed port (50800 in these captures).','Confirms TCP, but not HTTP, framing, local-only binding, source filtering, authentication or LAN availability.','Next evidence: saved listener/client code or unit/socket configuration. Refusal from the LAN alone cannot distinguish binding, filtering and service state.','High for TCP/port; other protocol properties unknown.','diagnostic lead')
        if 'Accepted TCP connection' in s:
            return annotation('MDC / scanner interface','MDCIF reports accepting a TCP connection and prints peer fields.','Shows a client connects in this boot. Peer 0.0.0.0:0 is not reliable proof of a localhost client or the actual source address.','Correlate the adjacent command/NVS messages; an authorized socket/process map is needed to identify the client.','High for acceptance; peer identity unknown.','diagnostic lead')
        if re.search('command processing',s,re.I):
            return annotation('MDC / scanner interface','MDCIF enters its command-processing phase after the connection.','Establishes ordering, not a command format, API or permission to send arbitrary bytes.','Locate matching client serialization and documented read-only operations before any protocol interaction.','High for printed stage; framing unknown.','diagnostic lead')
        if 'initNVSHiLevelFunction' in s:
            return annotation('MDC / settings initialization','MDCIF enters initNVSHiLevelFunction before announcing its listener.','Internal initialization marker. NVS plausibly refers to nonvolatile settings/storage, but the expansion and backing data are not proved.','Inspect matching function/source or vendor documentation; do not equate this with SettingsDebugLevel.','High for function name/order; expansion inferred.','diagnostic lead')
        if 'primeNVSSystem' in s:
            return annotation('MDC / settings initialization','MDCIF reports primeNVSSystem in the post-connection initialization sequence.','Suggests internal settings/state preparation; no specific remote command or call stack is captured.','Use the adjacent accepted/processing/data-filled markers to compare startup timing; matching code is needed for causality.','High for sequence; exact operation unknown.','diagnostic lead')
        if 'u8NVSMembersDataFilledIn' in s:
            return annotation('MDC / settings initialization','Sets/reports the internal u8NVSMembersDataFilledIn marker with “ver 4”.','The name suggests a data-filled/state-version marker; u8 plausibly denotes an unsigned byte. It is not proved to be an EWS setting, debug level, firmware version or user-writable control.','Locate the exact field definition and writer/reader call sites. In saved boots it follows connection/command setup and primeNVSSystem.','High for text/order; type and semantics inferred.','diagnostic lead')
        if 'ADF' in s or 'JAM_REMAINDER' in s:
            return annotation('MDC / scanner sensors','MDCIF reports the printed automatic-document-feeder cover state.','Useful physical-state timeline. A cover/jam-remainder label is not proof a particular card image was lost, nor is the MDC time proven UTC.','Correlate this exact event with a scan ID, application error and image/upload acknowledgement; do not infer missing data from a cover transition alone.','High for reported sensor state; physical cause and job linkage unverified.','diagnostic lead')
        if re.search('closed|Closing|Reopening',s,re.I):
            return annotation('MDC / shutdown','MDCIF reports this socket close/reopen operation during the saved orderly-shutdown sequence.','Does not establish a spontaneous fault or identify which endpoint/client initiated closure.','Interpret with nearby ScanEngine/MDC stop records; matching code is needed for socket ownership.','High for operation and shutdown context.','shutdown')
    if '_wake_scheduler' in s:
        return annotation('Scanner driver initialization','A scheduler wake is attempted before that scheduler is initialized.','Repeated startup error text; it is not tied to an active card scan. Could be initialization-order noise or a defect requiring vendor interpretation.','Compare with successful boots and runtime occurrences; request matching driver logs/source before assigning causality.','High for error text; impact unknown.','warning/error')
    if 'scan_queue_prune' in s:
        return annotation('Scanner driver initialization','The specifically named Scan queue cannot find side 0/page_id 0 for pruning.','Occurs during startup across Scan0–Scan9. It is not evidence that a real job’s page ID was discarded or that image bytes persist.','Correlate real job/page IDs and runtime queue events separately; identify the queue consumer in vendor code.','High for queue/error fields; application impact unknown.','warning/error')
    if 'stmotor_BaseFreq' in s:
        return annotation('Scanner motor initialization','Motor/PWM setup obtains a zero ratio and forces it to 1.','A fallback during initialization; it does not on its own diagnose feed/jam failures.','Compare with healthy startup and vendor motor diagnostics before considering a settings change.','High for fallback; impact unknown.','warning/error')
    if 'pwm pwmchip0: Bad values' in s:
        return annotation('Scanner / PWM','PWM rejects this printed c0/c1 combination.','Startup warning, also seen with different c1 values; not proof of a runtime scan failure.','Keep exact values and correlate with a matching symptom and vendor driver interpretation.','High for warning; cause/impact unknown.','warning/error')
    if 'mlock_shared_object' in s:
        return annotation('MDC process initialization','A request to find/lock the named shared-library pattern in RAM fails.','Memory-locking/lookup failure is not the same as failure to load the library. The process continues into MDC initialization.','Matching code and unit limits can explain the optimization/latency impact; do not infer missing libraries or an access route.','High for failure; exact failure branch unknown.','warning/error')
    if 'TPM error' in s:
        return annotation('TPM initialization','The TPM driver reports raw error 256 during a self-test attempt.','A real startup diagnostic, but subsequent TPM/Azure services start. This alone does not prove broken enrollment or lost uploads.','Use version-matched TPM/vendor diagnostics to decode the result and correlate identity-service errors; no key extraction.','High for raw result; decoding/impact unresolved.','warning/error')
    if 'lbtrace:' in s or 'LBTRACE driver' in s:
        return annotation('Vendor tracing driver','Loads/starts LBTRACE; the specific line may flag out-of-tree or proprietary-module kernel taint.','Evidence of vendor tracing infrastructure. Taint flags describe support/provenance conditions, not proof of malware or a crash.','Find LBTRACE configuration/output sinks and matching source/symbols via authorized artifacts [S10].','High for module event; trace destination unknown.','diagnostic lead')
    if 'Collecting audit messages is disabled' in s or 'Journal Audit Socket was skipped' in s:
        return annotation('Host logging','Kernel-audit collection/socket activation is disabled or conditionally skipped.','This does not disable journald, syslog, Docker logging or all diagnostic messages.','Inspect each log pipeline separately; do not interpret this as a universal logging switch.','High','routine')
    if 'Huge Pages File System was skipped' in s:
        return annotation('Kernel/userspace mount setup','Skips hugetlbfs because the expected hugepages path is absent.','Conditional capability handling, not a failed image allocation.','No action unless a specific application requires huge pages.','High','routine')
    if 'event_loop' in s and re.search('closed|reestablish',s,re.I):
        return annotation('Scanner IPC / shutdown','An event loop notices a connection closure and attempts reestablishment during recorded shutdown.','Expected shutdown context is stronger than a spontaneous crash interpretation; component/endpoint is not fully identified by this line.','Correlate adjacent ScanEngine/MDC stop and socket-close records; inspect matching source for ownership.','High for text/context; owner uncertain.','shutdown')
    if 'Unable to finalize remaining DM devices' in s:
        return annotation('System shutdown','Final shutdown cannot finish remaining device-mapper devices and explicitly continues.','Shutdown warning; it does not prove the device crashed or scan data was corrupted.','If shutdown integrity is a symptom, request preceding unmount/device-mapper errors and mount definitions.','High for warning; cause unknown.','warning/error')
    if re.search('reboot: Power down|GMSoftOff|GM: Setting Soft Off',s):
        return annotation('System shutdown','Final power-down/soft-off marker in the recorded shutdown.','Confirms this capture includes an orderly poweroff path, not just a boot.','Use this boundary when interpreting preceding service closures; no power operation was performed for this report.','High','shutdown')
    if 'Deactivated swap /dev/zram0' in s:
        return annotation('System shutdown','Disables the zram0 compressed-RAM swap device during shutdown.','Part of orderly teardown; no persistent scan-image store or recovered data is shown.','Do not treat shutdown swap removal as the initiating scanning fault.','High','shutdown')
    if re.search('comp_req_free|comp_unbind|tx_req_list|rx_req_list',s):
        return annotation('USB gadget shutdown','USB composite/gadget teardown prints request/buffer/list cleanup details.','Consistent with shutdown; pointer/list values are not image files or recoverable image addresses.','Investigate only if a matching teardown fault occurs; no buffers were read.','Medium for cleanup role; proprietary fields undocumented.','shutdown')
    if re.search('vendor ID:|product ID:|bcdDevice:|iPrd:|iManufac:|iSerialNum:|iPNPstring:|comp_bind PNP:|qlen:|auto_enum:|forcefs:',s):
        meaning='USB gadget descriptor/configuration field: '+s.split(':',1)[0]+'.'
        fields=[('vendor ID:','Reports the gadget vendor-ID module parameter, here 0x0000.'),('product ID:','Reports the gadget product-ID module parameter, here 0x0000.'),('bcdDevice:','Reports the gadget device-release descriptor field.'),('iPrd:','Prints the gadget product string, “Lexmark xxxx”.'),('iManufac:','Prints the gadget manufacturer string.'),('iSerialNum:','Prints a short gadget serial-string value, apparently a template/default rather than verified device identity.'),('iPNPstring:','Prints a printer-style plug-and-play descriptor with template-like model/serial values.'),('comp_bind PNP:','Binds/prints the composite gadget’s PNP descriptor.'),('qlen:','Reports gadget queue-length configuration (5).'),('auto_enum:','Reports gadget auto-enumeration flag (0); exact behavior needs driver code.'),('forcefs:','Reports gadget forcefs flag (0), plausibly force-full-speed; expansion is not proven here.')]
        for k,m in fields:
            if k in s:meaning=m;break
        if 'Starting Remount' in s:meaning='Interleaved systemd remount-start text and USB gadget vendor-ID output. '+meaning
        return annotation('USB gadget initialization',meaning,'Describes Linux USB device-mode presentation, distinct from the earlier host controllers. Template-like T62x AIO/SN values are not reliable identification of this sifter.','Read the matching gadget driver/configuration to establish the intended host protocol; no USB installer or boot keyboard capability is proved.','High for printed field; vendor-specific semantics/template status inferred.','routine')
    if re.search('using d4224000.usb3dev|scan OUT ep|hid IN ep',s):
        return annotation('USB gadget initialization','Assigns the printed USB gadget IN/OUT endpoints to the general, scan or HID function.','Scanner-related USB endpoints are a concrete interface lead, but endpoint numbers are not TCP ports and do not define framing or commands.','Use matching authorized driver/client documentation to identify the protocol; no guessed USB traffic.','High for endpoint mapping; protocol unknown.','diagnostic lead')
    if re.search('Expecting device|Found device',s):
        name=re.split(r'(?:Expecting|Found) device ',s)[-1].rstrip('.')
        isdata='/by-label/data' in s
        return annotation('Device discovery',('Waits for' if 'Expecting' in s else 'Discovers')+' '+name+'.',('The data label is a useful writable-storage lead; it does not identify a scan spool.' if isdata else 'This network interface exists/is expected; no association, link or cloud connectivity is established.'),('Match the data label to a partition and /var mount using an authorized mount inventory.' if isdata else 'Correlate interface-specific status/logs if uploads fail.'),'High','diagnostic lead' if isdata else 'routine')
    ss=re.sub(r'^systemd\[\d+\]:\s*','',s)
    ss=re.sub(r'^\[\s*OK\s*\]\s*','',ss)
    m=re.match(r'(Reached target|Stopped target|Created slice|Removed slice) (.*)',ss)
    if m:
        action,name=m.groups()
        rel='A dependency/cgroup lifecycle boundary; it does not independently prove application readiness or failure.'
        lead='Use individual service and application records to determine health.'
        if 'Login Prompts' in name:rel='Reaching this target does not prove a serial getty, working UART input or usable login.';lead='A specific getty unit and authorized authentication path are still required.'
        elif 'Network' in name:rel='Network dependency ordering; not proof of Internet/Azure connectivity or successful image delivery.';lead='Correlate actual upload acknowledgement/retry evidence for the same scan.'
        elif 'Hardware activated USB' in name:rel='USB gadget lifecycle target; no supported USB skill-install route is shown.';lead='Inspect OEM-supported USB workflows and actual gadget configuration.'
        elif 'Time' in name:rel='Time-related dependency target; no NTP synchronization success is established.';lead='Verify actual time synchronization before matching cloud timestamps.'
        elif 'Shutdown' in name or 'Power Off' in name or 'Unmount' in name:rel='Places nearby events in orderly shutdown rather than normal scanning.';lead='Do not misclassify planned service/socket teardown as the initiating fault.'
        return annotation('Systemd targets / resource groups',action+' '+name.rstrip('.')+'.',rel,lead,'High','shutdown' if action.startswith(('Stopped','Removed')) or 'Shutdown' in name or 'Power Off' in name else 'routine')
    m=re.match(r'(Starting|Started|Finished|Stopping|Stopped|Listening on|Closed|Mounting|Mounted|Unmounting|Unmounted) (.*)',ss)
    if m:
        state,name=m.groups();name=name.rstrip('.')
        for pat,role,rel,lead in UNITS:
            if pat.search(name):
                return annotation('Systemd service/socket lifecycle',state+' '+name+': '+role+'. '+state_explanation(state),rel,lead,level='shutdown' if state in ('Stopping','Stopped','Closed','Unmounting','Unmounted') else 'diagnostic lead' if re.search('log|trace|scanner|MDC|settings|container|storage',role,re.I) else 'routine')
        if name.startswith('/'):
            rel='Mount lifecycle for this exact path; filesystem type and application contents are not shown.';lead='Use the saved mount unit/configuration to identify backing storage and durability.'
            if '/var/lib/docker/overlay2' in name:rel='Actual Docker overlay2 merged mounts are present. This does not identify persistent image files, volumes or the backing filesystem.';lead='An authorized container mount/volume inventory is needed to locate any persisted scan data.'
            elif '/run/docker/netns/' in name:rel='Docker network-namespace mount teardown, not image-data deletion.';lead='No image-recovery lead follows from namespace identifiers.'
            elif name=='/var':rel='Concrete writable-state mount candidate; no scan spool or log retention is identified.';lead='Request mount type/options, usage and application paths through a supported export.'
            elif name in ('/var/volatile','/srv'):rel='Potential volatile runtime storage; no scan-image use is shown.';lead='Confirm backing mount and consumer before assuming data survives reboot.'
            elif name=='/etc/machine-id':rel='Transient identity-file mount lifecycle; not device de-enrollment or cloud credential removal.';lead='Keep machine ID separate from tenant/device authorization.'
            elif name=='/var/lib/docker':rel='Confirms a separate Docker storage mount at shutdown; no image-file persistence or storage driver config is printed.';lead='Obtain mount and container volume/log-driver inventory through authorized support.'
            return annotation('Filesystem / mount lifecycle',state+' '+name+'. '+state_explanation(state),rel,lead,'High for mount event; backing storage unknown.','shutdown' if state.startswith('Unmount') else 'diagnostic lead')
    return annotation('Unresolved captured text','This line is not yet matched to an established component or message interpretation.','Do not infer a protocol, error cause or recovery route from undocumented text.','Review adjacent source lines and matching vendor code.','Unresolved','UNREVIEWED')

def sha(b):return hashlib.sha256(b).hexdigest()
captures=[]; rows=[]; raw_records=[]
for p in sorted(SRC.iterdir()):
    if not p.is_file():continue
    b=p.read_bytes();ls=lines(b)
    kind='UART text/test'
    if p.suffix=='.json':kind='Capture metadata (not UART output)'
    if p.suffix=='.jsonl':kind='EWS telemetry (not UART output)'
    if p.name=='job-watch-live.log':kind='Timestamped UART byte records'
    if p.name=='job-watch-live-decoded.txt':kind='Previously decoded derivative of timestamped UART capture'
    if p.name=='screen-before-restart-20261028.txt':kind='Terminal scrollback: late startup, runtime cover events and orderly shutdown'
    captures.append(dict(file=p.name,bytes=len(b),physical_lines=len(ls),nonblank=sum(bool(x.strip(b'\r \t')) for x in ls),sha256=sha(b),kind=kind,covered=p.suffix in ('.log','.txt')))
    if p.suffix not in ('.log','.txt'):continue
    for n,line in enumerate(ls,1):
        if p.name=='job-watch-live.log':
            t,h=line.decode().split(' ',1);raw_records.append((n,t,bytes.fromhex(h)));continue
        text=clean(line.decode('utf8','replace'));v=interpret(text,p.name,n)
        rows.append(dict(capture=p.name,line=n,original_line_sha256=sha(line),text=redact(text),source_escaped=raw_display(line),receipt_prefixes=STAMP.findall(line.decode('utf8','replace')),**v))

# Reassemble hex fragments before interpreting them. This both restores complete
# messages and prevents a credential/identifier split across chunks escaping audit.
joined=b''.join(x[2] for x in raw_records)
masked=joined
for pat in (rb'systemd\.machine_id=[^\s]+',rb'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b',rb'/run/docker/netns/[^\s.]+',rb'libcontainer container [^\r\n]+',rb'(?i)(?:password|passwd|access_token|refresh_token|authorization|sharedaccesskey|client_secret)\s*[:=]\s*\S+'):
    masked=re.sub(pat,lambda m:b'X'*len(m.group()),masked)
assert len(masked)==len(joined)
offsets=[];pos=0
for n,t,b in raw_records:offsets.append((pos,pos+len(b),n,t));pos+=len(b)
derived=[];pos=0
for n,b in enumerate(lines(joined),1):
    start=pos;end=pos+len(b);pos=end+1
    # Include the terminating LF: a record may contain only that delimiter.
    covered_end=min(end+1,len(joined))
    touched=[x for x in offsets if x[0] < max(covered_end,start+1) and x[1]>start]
    # LF-only blank lines still map to the record containing their delimiter.
    if not touched:touched=[x for x in offsets if x[0]<=start<x[1]]
    v=interpret(b.decode('utf8','replace'),'job-watch-live.reconstructed',n)
    derived.append(dict(capture='job-watch-live.reconstructed',line=n,original_line_sha256=sha(b),text=redact(clean(b.decode('utf8','replace'))),source_escaped=raw_display(b),record_lines=[x[2] for x in touched],receipt_first=touched[0][3] if touched else '',receipt_last=touched[-1][3] if touched else '',**v))
for start,end,n,t in offsets:
    linked=[x for x in derived if n in x['record_lines']]
    linknums=[x['line'] for x in linked]
    # Each original raw record is individually represented, including fragments.
    v=annotation('Timestamped UART byte record',f'Host received {end-start} UART bytes at {t}; fragments contribute to reconstructed line(s) '+', '.join(map(str,linknums))+'.','A receipt timestamp applies to this byte chunk, not necessarily a complete device message or UTC. Interpret the reassembled message(s), not isolated hex bytes.','Read the linked reconstructed entries for the component-specific meaning, goal relevance and next verification.','High for byte mapping; host timezone and transport delay unverified.','capture record')
    rows.append(dict(capture='job-watch-live.log',line=n,original_line_sha256=sha((t+' '+joined[start:end].hex()).encode()),text=t+' '+masked[start:end].hex(),source_escaped=t+' '+masked[start:end].hex(),record_links=linknums,redaction_note='X bytes replace identity-bearing substrings before re-encoding; length and chunk mapping are preserved.' if masked[start:end]!=joined[start:end] else '',**v))

def sanitize(value):
    if isinstance(value,str):return redact(value)
    if isinstance(value,list):return [sanitize(x) for x in value]
    if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items()}
    return value
# Descriptions can interpolate a unit/path label, so sanitize every field, not
# just the original-line quote. Keep hashes for exact original-byte accounting.
rows=[sanitize(r) for r in rows]
derived=[sanitize(r) for r in derived]
bycap=collections.defaultdict(list)
for r in rows+derived:bycap[r['capture']].append(r)
for cap in bycap:bycap[cap].sort(key=lambda x:x['line'])
unreviewed=[r for r in rows+derived if r['classification']=='UNREVIEWED']
(OUT/'review-needed.json').write_text(json.dumps([{'capture':r['capture'],'line':r['line'],'text':r['text']} for r in unreviewed],indent=2))
print(json.dumps({'source_files':len(captures),'covered_source_lines':len(rows),'reconstructed_lines':len(derived),'unreviewed_count':len(unreviewed),'unique_unreviewed':sorted(set(r['text'] for r in unreviewed))},indent=2))

assert not unreviewed, 'Review every unmatched message before final generation.'
for cap in captures:
    if cap['covered']:
        assert [x['line'] for x in bycap[cap['file']]]==list(range(1,cap['physical_lines']+1)),cap['file']
assert sum(len(x[2]) for x in raw_records)==len(joined)
assert all(r['record_links'] for r in rows if r['capture']=='job-watch-live.log')

# Collapse display rows only when their redacted original text AND annotation
# are identical and adjacent. The separate line index retains every line.
groups={};entries={};line_map=[];nextid=1
for cap,rs in bycap.items():
    gs=[]
    for r in rs:
        data={k:v for k,v in r.items() if k not in ('capture','line')}
        if gs and gs[-1]['data']==data and gs[-1]['end']==r['line']-1:
            gs[-1]['end']=r['line'];eid=gs[-1]['id']
        else:
            eid=f'e{nextid}';nextid+=1
            gs.append(dict(id=eid,start=r['line'],end=r['line'],data=data));entries[eid]=dict(capture=cap,first_line=r['line'],**data)
        line_map.append(dict(capture=cap,line=r['line'],entry=eid))
    groups[cap]=gs
for cap,gs in groups.items():
    assert sum(g['end']-g['start']+1 for g in gs)==len(bycap[cap])
    for g in gs:entries[g['id']]['last_line']=g['end']

SOURCES=[
('S1','Linux dm-verity','https://docs.kernel.org/admin-guide/device-mapper/verity.html'),
('S2','Linux ramoops persistent RAM crash records','https://docs.kernel.org/admin-guide/ramoops.html'),
('S3','systemd journal storage configuration','https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html'),
('S4','systemd socket units','https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html'),
('S5','U-Boot FIT images','https://docs.u-boot.org/en/latest/usage/fit/index.html'),
('S6','Linux kernel command-line parameters','https://docs.kernel.org/admin-guide/kernel-parameters.html'),
('S7','Docker logging-driver configuration','https://docs.docker.com/engine/logging/configure/'),
('S8','Azure IoT Edge security manager','https://learn.microsoft.com/en-us/azure/iot-edge/iot-edge-security-manager'),
('S9','systemd pstore archival','https://www.freedesktop.org/software/systemd/man/latest/systemd-pstore.service.html'),
('S10','Linux kernel taint flags','https://docs.kernel.org/admin-guide/tainted-kernels.html'),
('S11','Linux SquashFS','https://docs.kernel.org/filesystems/squashfs.html')]

DESCRIPTIONS={
'boot-full-jrip1-pin2.log':'Baseline A. Most complete early-firmware/kernel view used for interpretation. Ends while Docker is starting, so the filename “full” must not be read as proof of a completed operational boot. RTC anchor: 2026-10-28 21:28:54 UTC.',
'boot-jrip1-20261028T221520Z.log':'Boot B. Separate early-to-runtime capture; RTC anchor 2026-10-28 22:15:40 UTC. Continues through Docker, Azure IoT Edge, an individual container, and MDC post-connection initialization.',
'job-watch-live.log':'Boot C raw source. Each line is host receipt time plus hexadecimal UART bytes; chunk boundaries do not equal message boundaries. Identity-bearing byte spans are masked before hex rendering. Follow each record’s links to reconstructed message annotations.',
'job-watch-live.reconstructed':'Boot C reconstructed from all 978 raw records, without inserting host timestamps into the UART bytes. Each entry lists contributing raw record numbers and its first/last host receipt time. This derived view extends beyond the previously decoded file to later cover-state events.',
'job-watch-live-decoded.txt':'An existing derivative of Boot C, not another independent boot. Embedded receipt timestamps are separated from message text for readability. Some original UTF-8/ANSI fragments were already damaged by timestamp insertion; the reconstructed raw source is preferred for interpretation.',
'boot-115200-jrip1-pin2.log':'Partial late-startup capture. Earlier firmware/kernel output is absent; it must not be silently prepended to another boot. MDC initial setup/listener occurs near 8.909 seconds on its own printed clock.',
'screen-before-restart-20261028.txt':'Terminal scrollback with 100,055 physical lines, predominantly blanks. Contains late startup, delayed MDC connection near 182.681, later cover events near 4,881–4,885, and orderly service teardown/poweroff near 4,889. No early RTC anchor in this retained segment establishes its relation to the other boots.',
'boot-115200-r3.log':'Large PING/echo test artifact (7 physical lines), not a boot sequence or proof of a working shell. Long lines are preserved in expandable source text.',
}

def esc(s):return html.escape(str(s),quote=True)
def cite(s):
    s=esc(s)
    return re.sub(r'\[S(\d+(?:,S\d+)*)\]',lambda m:'['+', '.join(f'<a href="#S{x}">S{x}</a>' for x in m.group(1).split(',S'))+']',s)
def anchor(cap):return re.sub(r'[^a-zA-Z0-9_-]','-',cap)
def ref(cap,n,label=None):return f'<a href="#{anchor(cap)}-L{n}" data-jump="{esc(cap)}:{n}">{esc(label or cap+":"+str(n))}</a>'

summary=f'''<section class="intro"><p class="eyebrow">ROCA SIFTER · SAVED UART EVIDENCE · 31 OCTOBER 2026</p>
<h1>Every boot line, explained</h1><p class="lede">The captures identify a Lexmark Yocto Linux host with a read-only verified root, separate writable mounts, Docker/IoT Edge, scanner IPC and an MDC TCP listener. They reveal useful diagnostic destinations, but they do not contain a per-card image-retention policy, a proven interactive shell, or the cause of a particular failed upload.</p>
<div class="metrics"><div><b>{sum(c['covered'] for c in captures)}</b> UART/text source files</div><div><b>{len(rows):,}</b> source lines mapped</div><div><b>{len(derived)}</b> reassembled UART lines</div><div><b>0</b> unmatched annotations</div></div>
<p>Each entry gives the observed meaning, relevance to scanning failures/missing images/internal settings/log access, a useful next verification, and confidence. Routine lines explicitly carry low direct relevance. Original captures were read only; no device, network, USB, reset, settings or cloud action was performed.</p>
<h2>The strongest diagnostic leads</h2><ol>
<li><strong>Crash records and host logs already have configured infrastructure.</strong> Ramoops reserves 1 MiB; journald, syslog, persistent-journal flushing and pstore archival start. These are concrete places to request an authorized support export, not evidence their contents are presently accessible or retained. See {ref('boot-full-jrip1-pin2.log',196,'A:196–198')}, {ref('boot-full-jrip1-pin2.log',568,'A:568–573')}, {ref('boot-full-jrip1-pin2.log',631,'A:631–645')}.</li>
<li><strong>Port 50800 is explicitly TCP and belongs to the MDC startup sequence.</strong> A client later connects, command processing starts, then NVS priming and the “ver 4” marker appear. HTTP, binding address, client identity and request framing are not established. See {ref('boot-full-jrip1-pin2.log',670,'A:670–671')} and the MDC entries in Boot B/C.</li>
<li><strong>The scanner has named local IPC interfaces.</strong> LxkScanDataRemote, ScanEngine RPC and membroker sockets are created. Their unit definitions and matching clients are the next evidence needed to learn transport and safe read-only requests. These names do not prove a mapping to port 21586. See {ref('boot-full-jrip1-pin2.log',602,'A:602–604')}.</li>
<li><strong>Storage exists, but missing-image persistence is unresolved.</strong> eMMC has eight logical partitions; root uses dm-verity/SquashFS; /var, volatile paths and Docker storage appear. Shutdown includes actual overlay2 mounts. None proves a durable scan-image spool. See {ref('boot-full-jrip1-pin2.log',350,'A:350–376')}, {ref('boot-full-jrip1-pin2.log',561,'A:561–577')} and the scrollback mount teardown.</li>
<li><strong>Startup warnings are a baseline, not a diagnosis.</strong> Scheduler-before-init, Scan0–Scan9 pruning with page_id 0, PWM, TPM and memory-locking warnings occur during initialization. The retained shutdown also includes planned socket closures. Match a real scan ID/time and application failure before assigning cause.</li></ol>
<h2>What this changes about the next investigation</h2><p>The best next evidence is a supported local/vendor export of existing journal/syslog/pstore records, scanner service/socket definitions, and the application container’s log-driver and mount inventory. Existing saved frontend/settings artifacts can identify consumers without touching the device. The crucial application evidence remains a scan/page identifier, acquisition result, buffer/spool path if any, upload attempt/retry and server acknowledgement. RAM-only, persisted, uploaded-but-unindexed and deleted images require different recovery paths; this boot output cannot choose among them.</p>
<p>A factory reset is not supported by these logs as a way to unlock diagnostics. “Box line reset if /var/blurb exists” is a conditional unit label, not a documented owner reset procedure. Linux USB host/HID support does not prove bootloader keyboard input, and USB gadget scan endpoints do not establish a USB skill installer.</p>
<h2>How to read time and confidence</h2><ul>
<li><strong>Source-line numbering:</strong> physical LF-delimited lines in original bytes, starting at 1. CR and ANSI escapes do not add source lines. No extra empty line is counted after a final LF. Blank and NUL-only lines are retained.</li>
<li><strong>Text display:</strong> normal view removes CR/ANSI decoration. Expand “source text” for escaped control bytes. The existing decoded derivative’s inserted host timestamps are removed from text and listed separately. Invalid UTF-8 bytes are represented rather than treated as meaningful messages. Redactions preserve line placeholders.</li>
<li><strong>Duplicate display ranges:</strong> only adjacent entries with identical redacted original text and annotations are collapsed. Every source line still maps to its entry in <code>line-map.jsonl</code>. Equal messages with different times/fields are not merged.</li>
<li><strong>Clocks:</strong> RTC messages explicitly provide UTC; they still depend on RTC correctness. Firmware/kernel build dates are build metadata, not boot time. MDC “At” values look like elapsed seconds but the clock’s implementation is unverified. Host HH:MM:SS.mmm values are byte-receipt times with no recorded timezone here; they are not device event timestamps. Do not subtract clocks from different captures.</li>
<li><strong>[O] versus [I]:</strong> quoted line/events are observations. Decoding standard Linux/systemd behavior uses primary documentation. Vendor acronym expansions, service purposes inferred from names and causal implications are explicitly limited. A successful systemd unit does not certify the whole application.</li></ul>
<h2>Boot-to-boot comparison</h2><table><thead><tr><th>Capture</th><th>Confirmed boundary / timing</th><th>Interpretation</th></tr></thead><tbody>
<tr><td>A · boot-full-jrip1-pin2.log</td><td>708 lines; RTC 21:28:54 UTC; MDC init 9.175206, listen 9.177602</td><td>Ends at Docker start/settings-network-online. No later connection is captured here.</td></tr>
<tr><td>B · boot-jrip1-20261028T221520Z.log</td><td>725 lines; RTC 22:15:40 UTC; MDC accepted 54.432209 → data-filled 54.548404</td><td>Connection-to-marker ≈116 ms on the same MDC clock. Sequence does not prove a remote command’s call chain.</td></tr>
<tr><td>C · timestamped UART source</td><td>978 byte records → 732 reconstructed lines; RTC 21:51:56 UTC; accepted 72.409031 → marker 72.528370</td><td>≈119 ms. Raw source continues to MDC cover events near 1,036 seconds; the old decoded file stops earlier.</td></tr>
<tr><td>Scrollback</td><td>100,055 lines; MDC accepted 182.681187 → marker 182.796617; orderly shutdown near 4,889 seconds</td><td>≈115 ms. No saved early clock anchor proves which other capture, if any, it overlaps.</td></tr>
<tr><td>Partial JRIP1 capture</td><td>183 lines; MDC init 8.908928, listen 8.910817</td><td>Late startup only. Do not splice into a full boot.</td></tr></tbody></table>
<p>Other differences include DDR training values, internal-temperature readings (32.8624 / 43.128 / 28.9584 in A/B/C; units not stated in these lines), journald process IDs, and interleaving/order of service messages. These variations alone do not identify a fault. The known user-supplied line <code>MDCIF: At 00133.072456 - setting u8NVSMembersDataFilledIn ver 4</code> is supplemental testimony: it was not found in these saved captures, so no neighboring context is fabricated for it.</p>
<h2>Limits that matter</h2><p>dm-verity and SHA verification establish integrity operations, not storage encryption or a complete secure-boot/fuse policy. Hostname “localhost” and the MDC peer fields “0.0.0.0:0” do not prove loopback binding. UART console output does not establish a getty or receive wiring. No observed boot countdown/key test is present. None of these captures ties SettingsDebugLevel=7 to a changed log sink or verbosity; no comparable controlled before/after baseline is included.</p></section>'''

inventory='<section id="inventory"><h2>Capture inventory and coverage</h2><p>Source directory: <code>device/uart</code> (private local evidence). All 24 .log/.txt files are covered, including empty files and tests. Two capture-metadata JSON files and one EWS telemetry JSONL file are inventoried but are not UART messages and are not passed off as boot lines. Full original SHA-256 values are in <code>coverage.json</code>.</p><table><thead><tr><th>Source</th><th>Bytes</th><th>LF lines</th><th>Nonblank</th><th>Scope</th></tr></thead><tbody>'
for c in captures:
    label=f'<a href="#{anchor(c["file"])}" data-cap="{esc(c["file"])}">{esc(c["file"])}</a>' if c['covered'] and c['physical_lines'] else esc(c['file'])
    inventory+=f'<tr><td>{label}</td><td>{c["bytes"]:,}</td><td>{c["physical_lines"]:,}</td><td>{c["nonblank"]:,}</td><td>{esc(c["kind"])}'+(' — empty, no lines to interpret' if c['bytes']==0 else '')+'</td></tr>'
inventory+='</tbody></table></section>'

order=['boot-full-jrip1-pin2.log','boot-jrip1-20261028T221520Z.log','job-watch-live.reconstructed','screen-before-restart-20261028.txt','boot-115200-jrip1-pin2.log','job-watch-live-decoded.txt','job-watch-live.log']
order += [c for c in bycap if c not in order]
controls='<section id="annotations"><h2>Line-by-line annotations</h2><div class="controls"><label>Capture <select id="capture">'+''.join(f'<option value="{esc(c)}">{esc(c)} ({len(bycap[c]):,} lines)</option>' for c in order)+'<option value="ALL">All captures</option></select></label><label>Find text or topic <input id="search" type="search" placeholder="pstore, 50800, warning…"></label><label>Source line <input id="line" type="number" min="1" placeholder="e.g. 671"></label><button id="go">Go</button><label class="check"><input id="important" type="checkbox"> Leads and warnings only</label><span id="visible" aria-live="polite"></span></div><p class="hint">Select a capture, search within it, or jump to an original line number. Each byte-record link opens the corresponding reconstructed message. Expand original source text for complete long lines.</p>'
body=[]
for cap in order:
    body.append(f'<section class="capture" id="{anchor(cap)}" data-name="{esc(cap)}"><h3>{esc(cap)}</h3><p>{esc(DESCRIPTIONS.get(cap,"Serial capture/test artifact. No semantic boot messages are inferred from empty or non-printing content."))}</p>')
    for g in groups[cap]:
        d=g['data'];a=g['start'];b=g['end'];label=str(a) if a==b else f'{a}–{b} (identical ×{b-a+1:,})'
        searchable=' '.join(str(d.get(k,'')) for k in ('text','stage','meaning','relevance','verification','classification')).lower()
        body.append(f'<article class="entry" id="{anchor(cap)}-L{a}" data-start="{a}" data-end="{b}" data-kind="{esc(d["classification"])}"><div class="entry-head"><span class="ln">Line {label}</span><span>{esc(d["stage"])}</span><span class="badge">{esc(d["classification"])}</span></div>')
        # Full text stays in source details, so enormous PING lines do not dominate.
        text=d['text'] or '[blank / non-printing capture line]'
        body.append('<pre class="message">'+esc(text if len(text)<1800 else text[:1800]+'\n[Display excerpt; complete original line is preserved below.]')+'</pre>')
        if d.get('receipt_first'):body.append(f'<p class="meta">Host receipt {esc(d["receipt_first"])}–{esc(d["receipt_last"])} · raw record lines '+', '.join(ref('job-watch-live.log',n,str(n)) for n in d['record_lines'])+'</p>')
        if d.get('receipt_prefixes'):body.append('<p class="meta">Inserted host receipt stamps: '+esc(' '.join(d['receipt_prefixes']))+'</p>')
        if d.get('record_links'):body.append('<p class="meta">Reconstructed messages: '+', '.join(ref('job-watch-live.reconstructed',n,str(n)) for n in d['record_links'])+'</p>')
        for key,label2 in [('meaning','Meaning [O/I]'),('relevance','Why it matters'),('verification','Next verification'),('confidence','Confidence / limits')]:body.append(f'<p><b>{label2}:</b> {cite(d[key])}</p>')
        if d.get('variant_note'):body.append('<p class="meta">'+esc(d['variant_note'])+'</p>')
        if d.get('redaction_note'):body.append('<p class="meta">'+esc(d['redaction_note'])+'</p>')
        body.append('<details><summary>Source text (escaped controls; redactions marked)</summary><pre>'+esc(d['source_escaped'] or '[empty physical line]')+'</pre></details></article>')
    body.append('</section>')
body.append('</section>')
references='<section id="references"><h2>Primary references</h2><p>These sources explain standard mechanisms. They do not establish this OEM’s undocumented configuration. Current online manuals may describe newer releases than the device’s systemd 255, U-Boot 2022.01 or IoT Edge build; use the log and matching source for device-specific behavior. No security research findings are transferred to this board as proof of an exploit, pinout or access path.</p><ol>'+''.join(f'<li id="{n}"><a href="{url}">{n}: {esc(title)}</a></li>' for n,title,url in SOURCES)+'</ol></section>'

css='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f6f7;color:#17232d;font:16px/1.58 system-ui,-apple-system,sans-serif}main{max-width:1170px;margin:auto;padding:44px 30px 80px}h1{font-size:46px;line-height:1.1;letter-spacing:-1.4px;margin:12px 0 24px}h2{font-size:25px;margin-top:36px}h3{font-size:21px;overflow-wrap:anywhere}p{margin:12px 0}.eyebrow{font-size:12px;font-weight:750;letter-spacing:1.4px;color:#477080}.lede{font-size:20px;line-height:1.5}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0}.metrics div{border-top:3px solid #208578;background:#fff;padding:16px;font-size:13px}.metrics b{display:block;font-size:30px}section{scroll-margin-top:20px}a{color:#006e88}table{width:100%;border-collapse:collapse;background:white;font-size:13px;margin:18px 0;table-layout:auto}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #dfe6e9;vertical-align:top;overflow-wrap:anywhere}th{background:#e8eff2}td:first-child{max-width:300px}code{font-size:.9em;background:#e9eef1;padding:2px 4px;overflow-wrap:anywhere}.controls{position:sticky;top:0;z-index:2;display:flex;align-items:end;gap:12px;flex-wrap:wrap;background:#e2ebef;padding:16px;border:1px solid #cbd9e0;border-radius:8px}label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:650}input,select,button{font:inherit;font-size:14px;padding:9px;border:1px solid #a7bcc7;border-radius:4px;background:white;color:#17232d}select{max-width:370px}#line{width:96px}button{background:#116b79;color:white;cursor:pointer}.check{flex-direction:row;align-items:center;padding:8px 0}#visible,.hint,.meta{font-size:12px;color:#536b78}.entry{background:#fff;border:1px solid #dce5e9;border-radius:8px;margin:16px 0;padding:20px 24px;scroll-margin-top:155px}.entry-head{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:12px;color:#526b78}.ln{font-weight:750;color:#123b4d}.badge{margin-left:auto;background:#edf3f5;border-radius:20px;padding:3px 9px}.entry[data-kind="warning/error"]{border-left:4px solid #c47731}.entry[data-kind="diagnostic lead"]{border-left:4px solid #208578}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;background:#f3f6f8;padding:12px;border-radius:4px}.message{color:#203b4c}.entry p{font-size:14px}.entry details{font-size:12px;color:#586c75;margin-top:14px}summary{cursor:pointer}.capture[hidden],.entry[hidden]{display:none}nav{display:flex;gap:20px;font-size:14px;flex-wrap:wrap}footer{margin-top:40px;color:#536b78;font-size:12px}@media(max-width:720px){main{padding:25px 15px}h1{font-size:35px}.metrics{grid-template-columns:repeat(2,1fr)}.entry{padding:16px}.controls{position:static}select{max-width:100%}table{font-size:11px}th,td{padding:7px}.entry-head{gap:7px}}@media print{.controls,nav{display:none}.capture[hidden],.entry[hidden]{display:block}body{background:#fff}main{padding:0;max-width:none}.entry{break-inside:avoid}details{display:none}h2{break-after:avoid}}'''
js='''const select=document.querySelector('#capture'), search=document.querySelector('#search'), important=document.querySelector('#important');const caps=[...document.querySelectorAll('.capture')];function filter(){let shown=0;for(const c of caps){c.hidden=select.value!=='ALL'&&c.dataset.name!==select.value;for(const e of c.querySelectorAll('.entry')){e.hidden=!!search.value&&!e.textContent.toLowerCase().includes(search.value.toLowerCase())||important.checked&&!['diagnostic lead','warning/error'].includes(e.dataset.kind);if(!c.hidden&&!e.hidden)shown++;}}document.querySelector('#visible').textContent=shown.toLocaleString()+' display entries';}function jump(cap,n){select.value=cap;search.value='';important.checked=false;filter();const c=caps.find(x=>x.dataset.name===cap);const e=c&&[...c.querySelectorAll('.entry')].find(x=>+x.dataset.start<=n&&+x.dataset.end>=n);if(e){e.scrollIntoView({block:'start'});history.replaceState(null,'','#'+e.id);}}[select,search,important].forEach(e=>e.addEventListener('input',filter));document.querySelector('#go').onclick=()=>jump(select.value,+document.querySelector('#line').value);document.addEventListener('click',e=>{const a=e.target.closest('a[data-jump],a[data-cap]');if(!a)return;e.preventDefault();if(a.dataset.jump){const k=a.dataset.jump.lastIndexOf(':');jump(a.dataset.jump.slice(0,k),+a.dataset.jump.slice(k+1));}else{select.value=a.dataset.cap;filter();document.querySelector('#annotations').scrollIntoView();}});filter();if(location.hash){const e=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(e&&e.classList.contains('entry'))jump(e.closest('.capture').dataset.name,+e.dataset.start);}'''
doc='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Roca UART — Every boot line explained</title><style>'+css+'</style></head><body><main><nav><a href="#inventory">Inventory</a><a href="#annotations">Line annotations</a><a href="#references">References</a></nav>'+summary+inventory+controls+''.join(body)+references+'<footer>Prepared from saved local evidence on 2026-10-31. Original sources were not modified. This self-contained report makes no network requests.</footer></main><script>'+js+'</script></body></html>'
(OUT/'roca-uart-annotated.html').write_text(doc)
(OUT/'annotations.json').write_text(json.dumps(entries,ensure_ascii=False,separators=(',',':')))
with (OUT/'line-map.jsonl').open('w') as f:
    for x in line_map:f.write(json.dumps(x,separators=(',',':'))+'\n')
coverage=dict(source_root='device/uart',generated='2026-10-31',line_rule='LF-delimited physical lines; final LF does not create an extra empty line; CR/ANSI do not create new lines',source_files=captures,covered_source_lines=len(rows),derived_reconstructed_lines=len(derived),display_entries=len(entries),unreviewed=0,source_integrity='Original files read only; SHA-256 in inventory',redactions=['OS machine ID','MAC addresses if present','container and network-namespace IDs','Docker overlay layer identifiers','credential-like values if present'],tests=['Every covered source has contiguous 1..N line mappings','Every raw UART byte record maps to reconstructed message lines','Byte masking preserves length and record boundaries','No unresolved annotation remains','Only adjacent identical redacted text/annotations collapse into display ranges'])
(OUT/'coverage.json').write_text(json.dumps(coverage,indent=2))
(OUT/'README.txt').write_text('ROCA UART ANNOTATED REPORT\n\nOpen roca-uart-annotated.html in a browser. It is self-contained and makes no network requests.\n\ncoverage.json inventories original capture byte sizes, physical line counts and SHA-256 digests.\nline-map.jsonl maps every original physical line (and each reconstructed UART line) to an entry ID.\nannotations.json contains the full redacted original text and interpretation for each display entry.\n\nThe HTML collapses only adjacent identical redacted lines with identical annotations; each individual line remains in the index.\nRaw timestamp+hex UART records link to reassembled complete-message annotations.\nOriginal private captures are not included. No device actions or configuration changes were performed.\n')
bundle=OUT/'roca-uart-report.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in ['roca-uart-annotated.html','coverage.json','line-map.jsonl','annotations.json','README.txt']:z.write(OUT/name,name)
print(json.dumps({'report_bytes':(OUT/'roca-uart-annotated.html').stat().st_size,'bundle_bytes':bundle.stat().st_size,'display_entries':len(entries),'coverage_pass':True}))
