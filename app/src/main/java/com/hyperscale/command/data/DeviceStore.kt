package com.hyperscale.command.data

import android.content.Context
import android.util.Log
import com.hyperscale.command.core.model.Device
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Durable record of devices the user has seen before, plus the personal touches they have added:
 * nicknames, favourites and which devices they have adopted into their home.
 *
 * Deliberately a plain JSON file rather than a database. The dataset is a few hundred rows at
 * most, it is written once per scan, and keeping it as a single serialisable document means the
 * export/import feature is a file copy rather than a migration exercise.
 */
class DeviceStore(context: Context) {

    private val file = File(context.filesDir, FILE_NAME)
    private val mutex = Mutex()
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        prettyPrint = false
    }

    private val _devices = MutableStateFlow<List<Device>>(emptyList())

    /** Known devices from previous sessions. Seeds the discovery engine on launch. */
    val devices: StateFlow<List<Device>> = _devices.asStateFlow()

    suspend fun load(): List<Device> = mutex.withLock {
        val loaded = withContext(Dispatchers.IO) {
            runCatching {
                if (!file.exists()) return@runCatching emptyList<Device>()
                json.decodeFromString(ListSerializer(Device.serializer()), file.readText())
            }.getOrElse { error ->
                Log.w(TAG, "Could not read device store; starting fresh", error)
                emptyList()
            }
        }
        _devices.value = loaded
        loaded
    }

    suspend fun save(devices: List<Device>) = mutex.withLock {
        _devices.value = devices
        withContext(Dispatchers.IO) {
            runCatching {
                // Write to a temp file then rename, so a kill mid-write cannot corrupt the store.
                val temp = File(file.parentFile, "$FILE_NAME.tmp")
                temp.writeText(json.encodeToString(ListSerializer(Device.serializer()), devices))
                if (!temp.renameTo(file)) {
                    file.writeText(temp.readText())
                    temp.delete()
                }
            }.onFailure { error -> Log.w(TAG, "Could not persist device store", error) }
        }
    }

    /** Applies a user edit (nickname, favourite, adoption) and persists it immediately. */
    suspend fun update(deviceId: String, transform: (Device) -> Device) {
        val current = _devices.value
        val updated = current.map { device ->
            if (device.id == deviceId) transform(device) else device
        }
        save(updated)
    }

    suspend fun forget(deviceId: String) {
        save(_devices.value.filterNot { it.id == deviceId })
    }

    suspend fun clear() = save(emptyList())

    /** Serialises the whole store for the export feature. */
    fun exportJson(devices: List<Device>): String =
        exportFormat.encodeToString(ListSerializer(Device.serializer()), devices)

    private companion object {
        const val TAG = "DeviceStore"
        const val FILE_NAME = "devices.json"

        /** Held once: building a Json format is expensive enough not to do per call. */
        val exportFormat = Json {
            prettyPrint = true
            encodeDefaults = true
        }
    }
}
