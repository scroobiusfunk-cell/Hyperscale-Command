package com.hyperscale.command.discovery.scanners

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelUuid
import android.util.Log
import androidx.core.content.ContextCompat
import com.hyperscale.command.core.model.DiscoverySource
import com.hyperscale.command.core.model.Observation
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.ProtocolScanner
import com.hyperscale.command.discovery.ScanContext
import com.hyperscale.command.discovery.ScanDepth
import com.hyperscale.command.discovery.ScannerAvailability
import com.hyperscale.command.discovery.fingerprint.BluetoothCompanyIds
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Bluetooth Low Energy advertisement scanning.
 *
 * Advertisements are a surprisingly rich identity source: the 16-bit company identifier names the
 * vendor outright, and several ecosystems publish structured service data — Matter's commissionable
 * payload (0xFFF6) exposes vendor and product IDs, SwitchBot (0xFD3D) exposes device type and
 * battery, and HomeKit accessories (0xFD5A/0xFE07) advertise their pairing state.
 */
class BleScanner : ProtocolScanner {

    override val id = "ble"
    override val label = "Bluetooth LE"
    override val source = DiscoverySource.BLE

    override val protocols = setOf(
        Protocol.BLE, Protocol.BLE_MESH, Protocol.MATTER, Protocol.SWITCHBOT,
        Protocol.HOMEKIT, Protocol.GOVEE_LAN, Protocol.TUYA_LAN,
    )

    override fun availability(context: Context): ScannerAvailability {
        val manager = context.getSystemService(BluetoothManager::class.java)
            ?: return ScannerAvailability.Unavailable("No Bluetooth hardware")
        val adapter = manager.adapter
            ?: return ScannerAvailability.Unavailable("No Bluetooth adapter")

        if (!context.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) {
            return ScannerAvailability.Unavailable("Bluetooth LE not supported")
        }

        val permission = requiredPermission()
        if (ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED) {
            return ScannerAvailability.NeedsPermission(
                permission = permission,
                rationale = "Bluetooth scanning finds locks, sensors, trackers and Matter devices " +
                    "waiting to be commissioned. Hyperscale never uses it to derive your location.",
            )
        }

        if (!adapter.isEnabled) return ScannerAvailability.Unavailable("Bluetooth is turned off")
        if (adapter.bluetoothLeScanner == null) {
            return ScannerAvailability.Unavailable("Bluetooth LE scanner unavailable")
        }

        return ScannerAvailability.Ready
    }

    @SuppressLint("MissingPermission") // Guarded by availability(), re-checked below.
    override fun scan(scanContext: ScanContext): Flow<Observation> = callbackFlow {
        val context = scanContext.context
        if (!availability(context).isReady) {
            close()
            return@callbackFlow
        }

        val scanner = context.getSystemService(BluetoothManager::class.java)
            ?.adapter
            ?.bluetoothLeScanner
        if (scanner == null) {
            close()
            return@callbackFlow
        }

        val settings = ScanSettings.Builder()
            .setScanMode(
                when (scanContext.depth) {
                    ScanDepth.QUICK -> ScanSettings.SCAN_MODE_LOW_POWER
                    ScanDepth.STANDARD -> ScanSettings.SCAN_MODE_BALANCED
                    ScanDepth.DEEP -> ScanSettings.SCAN_MODE_LOW_LATENCY
                },
            )
            .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
            .apply {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    setLegacy(false)
                    setPhy(ScanSettings.PHY_LE_ALL_SUPPORTED)
                }
            }
            .build()

        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                result?.let { trySend(toObservation(it)) }
            }

            override fun onBatchScanResults(results: MutableList<ScanResult>?) {
                results?.forEach { trySend(toObservation(it)) }
            }

            override fun onScanFailed(errorCode: Int) {
                Log.w(TAG, "BLE scan failed with code $errorCode")
                close()
            }
        }

        runCatching {
            // An empty filter list scans everything; some OEMs throttle unfiltered background
            // scans, but this scan is always foreground and user-initiated.
            scanner.startScan(emptyList<ScanFilter>(), settings, callback)
        }.onFailure {
            Log.w(TAG, "Could not start BLE scan", it)
            close()
        }

        awaitClose { runCatching { scanner.stopScan(callback) } }
    }

    @SuppressLint("MissingPermission")
    private fun toObservation(result: ScanResult): Observation {
        val record = result.scanRecord
        val address = result.device?.address.orEmpty()
        val advertisedName = record?.deviceName?.trim()?.takeIf { it.isNotBlank() }

        val manufacturerData = record?.manufacturerSpecificData
        val companyId = if (manufacturerData != null && manufacturerData.size() > 0) {
            manufacturerData.keyAt(0)
        } else {
            null
        }
        val manufacturer = companyId?.let { BluetoothCompanyIds.nameFor(it) }

        val serviceUuids = record?.serviceUuids.orEmpty().map { it.uuid.toString().lowercase() }
        val serviceData: Map<ParcelUuid, ByteArray> = record?.serviceData.orEmpty()

        val protocol = identifyProtocol(serviceUuids, serviceData, companyId, advertisedName)
        val matter = serviceData.entries
            .firstOrNull { it.key.uuid.toString().startsWith(MATTER_UUID_PREFIX, ignoreCase = true) }
            ?.value
            ?.let(::parseMatterCommissioningPayload)

        return Observation(
            protocol = protocol,
            source = DiscoverySource.BLE,
            identityKeys = buildSet {
                if (address.isNotBlank()) add("ble:${address.lowercase()}")
                matter?.discriminator?.let { add("matterdisc:$it") }
            },
            macAddress = address.takeIf { it.isNotBlank() && !isRandomisedAddress(result) }?.lowercase(),
            displayName = advertisedName,
            manufacturer = manufacturer ?: matter?.vendorName,
            model = matter?.productDescription,
            rssi = result.rssi,
            attributes = buildMap {
                put("Address", address)
                put("Address type", if (isRandomisedAddress(result)) "Random (rotating)" else "Public")
                put("RSSI", "${result.rssi} dBm")
                result.txPower.takeIf { it != ScanResult.TX_POWER_NOT_PRESENT }
                    ?.let { put("Tx power", "$it dBm") }
                put("Connectable", result.isConnectable.toString())
                companyId?.let { put("Company ID", "0x%04X".format(it)) }
                if (serviceUuids.isNotEmpty()) put("Service UUIDs", serviceUuids.joinToString(", "))
                serviceData.forEach { (uuid, bytes) ->
                    put("Service data ${uuid.uuid.toString().take(8)}", bytes.toHex())
                }
                matter?.let {
                    put("Matter discriminator", it.discriminator.toString())
                    it.vendorId?.let { vid -> put("Matter vendor ID", "0x%04X".format(vid)) }
                    it.productId?.let { pid -> put("Matter product ID", "0x%04X".format(pid)) }
                    put("Matter state", "Commissionable — ready to pair")
                }
            },
            seenAtMillis = System.currentTimeMillis(),
        )
    }

    private fun identifyProtocol(
        serviceUuids: List<String>,
        serviceData: Map<ParcelUuid, ByteArray>,
        companyId: Int?,
        name: String?,
    ): Protocol {
        val uuids = (serviceUuids + serviceData.keys.map { it.uuid.toString().lowercase() })
        fun has(prefix: String) = uuids.any { it.startsWith(prefix, ignoreCase = true) }

        return when {
            has(MATTER_UUID_PREFIX) -> Protocol.MATTER
            has(SWITCHBOT_UUID_PREFIX) -> Protocol.SWITCHBOT
            has(HOMEKIT_UUID_PREFIX) || has(HOMEKIT_ALT_UUID_PREFIX) -> Protocol.HOMEKIT
            has(MESH_PROVISION_UUID_PREFIX) || has(MESH_PROXY_UUID_PREFIX) -> Protocol.BLE_MESH
            has(TUYA_UUID_PREFIX) -> Protocol.TUYA_LAN
            companyId == COMPANY_GOVEE || name?.startsWith("GV", ignoreCase = true) == true -> Protocol.GOVEE_LAN
            else -> Protocol.BLE
        }
    }

    /**
     * Matter commissionable node advertisement, per the Matter Core spec's BLE payload:
     * byte 0 opcode, bytes 1-2 discriminator (12 bits) plus version, bytes 3-4 vendor ID,
     * bytes 5-6 product ID, all little-endian.
     */
    private fun parseMatterCommissioningPayload(bytes: ByteArray): MatterPayload? {
        if (bytes.size < 7) return null
        val discriminator = ((bytes[1].toInt() and 0xFF) or ((bytes[2].toInt() and 0x0F) shl 8))
        val vendorId = (bytes[3].toInt() and 0xFF) or ((bytes[4].toInt() and 0xFF) shl 8)
        val productId = (bytes[5].toInt() and 0xFF) or ((bytes[6].toInt() and 0xFF) shl 8)
        return MatterPayload(
            discriminator = discriminator,
            vendorId = vendorId.takeIf { it != 0 },
            productId = productId.takeIf { it != 0 },
            vendorName = vendorId.takeIf { it != 0 }?.let { BluetoothCompanyIds.nameFor(it) },
            productDescription = productId.takeIf { it != 0 }?.let { "Matter product 0x%04X".format(it) },
        )
    }

    private data class MatterPayload(
        val discriminator: Int,
        val vendorId: Int?,
        val productId: Int?,
        val vendorName: String?,
        val productDescription: String?,
    )

    /**
     * Bit 1 of the first address octet marks a random (rotating) BLE address. Those must not be
     * used as identity keys — they change every 15 minutes and would fragment the device list.
     */
    @SuppressLint("MissingPermission")
    private fun isRandomisedAddress(result: ScanResult): Boolean {
        val address = result.device?.address ?: return true
        val firstOctet = address.substringBefore(':').toIntOrNull(16) ?: return true
        return (firstOctet and 0xC0) != 0x00
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02X".format(it) }

    private fun requiredPermission(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Manifest.permission.BLUETOOTH_SCAN
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }

    private companion object {
        const val TAG = "BleScanner"

        // Assigned 16-bit UUIDs expand to 0000XXXX-0000-1000-8000-00805f9b34fb.
        const val MATTER_UUID_PREFIX = "0000fff6"
        const val SWITCHBOT_UUID_PREFIX = "0000fd3d"
        const val HOMEKIT_UUID_PREFIX = "0000fe07"
        const val HOMEKIT_ALT_UUID_PREFIX = "0000fd5a"
        const val MESH_PROVISION_UUID_PREFIX = "00001827"
        const val MESH_PROXY_UUID_PREFIX = "00001828"
        const val TUYA_UUID_PREFIX = "0000fd50"

        const val COMPANY_GOVEE = 0x0157
    }
}
