package com.hyperscale.command.homey

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject

/**
 * Wire models for the Homey Pro local Web API.
 *
 * Several fields (titles, units) are localised objects on some firmware versions and plain
 * strings on others, so they are typed as [JsonElement] and read through [localisedText] rather
 * than being pinned to one shape and breaking on the other.
 */
@Serializable
data class HomeyDeviceDto(
    val id: String,
    val name: String? = null,
    val note: String? = null,
    val driverUri: String? = null,
    val driverId: String? = null,
    val zone: String? = null,
    val zoneName: String? = null,
    @SerialName("class") val deviceClass: String? = null,
    val virtualClass: String? = null,
    val available: Boolean = true,
    val ready: Boolean = true,
    val capabilities: List<String> = emptyList(),
    val capabilitiesObj: Map<String, HomeyCapabilityDto>? = null,
    val settings: JsonObject? = null,
    val flags: List<String> = emptyList(),
    val energy: JsonObject? = null,
    val images: JsonElement? = null,
    val iconObj: JsonElement? = null,
)

@Serializable
data class HomeyCapabilityDto(
    val id: String? = null,
    val type: String? = null,
    val title: JsonElement? = null,
    val desc: JsonElement? = null,
    val units: JsonElement? = null,
    val value: JsonElement? = null,
    val min: Double? = null,
    val max: Double? = null,
    val step: Double? = null,
    val decimals: Int? = null,
    val setable: Boolean = false,
    val getable: Boolean = true,
    val values: List<JsonElement>? = null,
    val lastUpdated: String? = null,
)

@Serializable
data class HomeyZoneDto(
    val id: String,
    val name: String? = null,
    val parent: String? = null,
    val icon: String? = null,
    val active: Boolean = false,
)

@Serializable
data class HomeySystemDto(
    val homeyVersion: String? = null,
    val homeyModelName: String? = null,
    val homeyModelId: String? = null,
    val hostname: String? = null,
    val nodeVersion: String? = null,
    val cloudId: String? = null,
    val wifiSsid: String? = null,
)

@Serializable
data class HomeyFlowDto(
    val id: String,
    val name: String? = null,
    val enabled: Boolean = true,
    val folder: String? = null,
    val broken: Boolean = false,
)

/**
 * Reads a field that may be a plain string or a localised map like `{"en": "Turned on"}`.
 * Prefers English, then any available language, then gives up.
 */
fun localisedText(element: JsonElement?): String? {
    if (element == null) return null
    return when (element) {
        is JsonPrimitive -> element.contentOrNullSafe()
        is JsonObject -> {
            val map = element.jsonObject
            (map["en"] ?: map.values.firstOrNull())
                ?.let { (it as? JsonPrimitive)?.contentOrNullSafe() }
        }

        else -> null
    }
}

private fun JsonPrimitive.contentOrNullSafe(): String? =
    if (!isString && content == "null") null else content.takeIf { it.isNotBlank() }

fun JsonElement?.asBooleanOrNull(): Boolean? =
    (this as? JsonPrimitive)?.booleanOrNull

fun JsonElement?.asDoubleOrNull(): Double? =
    (this as? JsonPrimitive)?.doubleOrNull

fun JsonElement?.asStringOrNull(): String? =
    (this as? JsonPrimitive)?.let { if (it.isString) it.content else it.content.takeIf { c -> c != "null" } }

/** Pulls a nested string out of the device `settings` blob without a schema. */
fun JsonObject?.settingString(key: String): String? =
    this?.get(key)?.let { element ->
        (element as? JsonPrimitive)?.content?.takeIf { it.isNotBlank() && it != "null" }
    }

/** Connection state for the Homey bridge, surfaced directly in the UI. */
sealed interface HomeyConnectionState {
    data object Disconnected : HomeyConnectionState
    data object Discovering : HomeyConnectionState
    data class Connecting(val address: String) : HomeyConnectionState
    data class Connected(
        val address: String,
        val system: HomeySystemDto?,
        val deviceCount: Int,
        val zoneCount: Int,
        val lastSyncMillis: Long,
    ) : HomeyConnectionState

    data class Failed(val address: String?, val reason: String) : HomeyConnectionState
}

/** A Homey Pro found on the LAN but not yet paired with the app. */
data class HomeyCandidate(
    val address: String,
    val hostname: String?,
    val modelName: String?,
    val version: String?,
)
