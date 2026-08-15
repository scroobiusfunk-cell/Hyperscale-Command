package com.hyperscale.command.homey

import android.util.Log
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Talks to a Homey Pro over its **local** Web API.
 *
 * Everything stays on the LAN: `http://<homey-ip>/api/manager/...` with a Personal Access Token
 * in an `Authorization: Bearer` header. No Athom cloud round-trip, so control works when the
 * internet is down and nothing about the house leaves the house.
 *
 * Two response envelopes exist across firmware generations — some endpoints return the payload
 * directly, others wrap it in `{"result": …}`. [unwrap] handles both rather than pinning to one.
 */
class HomeyClient(
    private val json: Json = defaultJson,
    private val httpClient: OkHttpClient = defaultClient(),
) {

    /** Result of an API call, so callers can show a real reason rather than a generic failure. */
    sealed interface HomeyResult<out T> {
        data class Success<T>(val value: T) : HomeyResult<T>
        data class Failure(val reason: String, val isAuthError: Boolean = false) : HomeyResult<Nothing>
    }

    suspend fun fetchSystem(address: String, token: String): HomeyResult<HomeySystemDto> =
        get(address, token, "/api/manager/system/") { element ->
            json.decodeFromJsonElement(HomeySystemDto.serializer(), element)
        }

    /**
     * Verifies an address + token pair. Returns the system info on success, which doubles as the
     * "is this really a Homey" check — a random web server on port 80 will not answer this.
     */
    suspend fun verify(address: String, token: String): HomeyResult<HomeySystemDto> =
        fetchSystem(address, token)

    suspend fun fetchDevices(address: String, token: String): HomeyResult<List<HomeyDeviceDto>> =
        get(address, token, "/api/manager/devices/device/") { element ->
            element.asObjectValues().mapNotNull { entry ->
                runCatching { json.decodeFromJsonElement(HomeyDeviceDto.serializer(), entry) }
                    .onFailure { Log.d(TAG, "Skipping unparseable device", it) }
                    .getOrNull()
            }
        }

    suspend fun fetchZones(address: String, token: String): HomeyResult<List<HomeyZoneDto>> {
        // v3 nests zones under /zone/; older firmware exposes them at the manager root.
        val primary = get(address, token, "/api/manager/zones/zone/") { element ->
            element.asObjectValues().mapNotNull { entry ->
                runCatching { json.decodeFromJsonElement(HomeyZoneDto.serializer(), entry) }.getOrNull()
            }
        }
        if (primary is HomeyResult.Success && primary.value.isNotEmpty()) return primary

        return get(address, token, "/api/manager/zones/") { element ->
            element.asObjectValues().mapNotNull { entry ->
                runCatching { json.decodeFromJsonElement(HomeyZoneDto.serializer(), entry) }.getOrNull()
            }
        }
    }

    suspend fun fetchFlows(address: String, token: String): HomeyResult<List<HomeyFlowDto>> =
        get(address, token, "/api/manager/flow/flow/") { element ->
            element.asObjectValues().mapNotNull { entry ->
                runCatching { json.decodeFromJsonElement(HomeyFlowDto.serializer(), entry) }.getOrNull()
            }
        }

    /**
     * Sets one capability on one device, e.g. `onoff` to true or `dim` to 0.4.
     *
     * The trailing slash matters: Homey's router is strict about it on capability writes.
     */
    suspend fun setCapability(
        address: String,
        token: String,
        deviceId: String,
        capabilityId: String,
        value: JsonElement,
    ): HomeyResult<Unit> = withContext(Dispatchers.IO) {
        val body = buildJsonObject { put("value", value) }.toString()
            .toRequestBody(JSON_MEDIA_TYPE)

        val request = Request.Builder()
            .url(baseUrl(address) + "/api/manager/devices/device/$deviceId/capability/$capabilityId/")
            .put(body)
            .header("Authorization", "Bearer $token")
            .header("Content-Type", "application/json")
            .build()

        execute(request) { HomeyResult.Success(Unit) }
    }

    suspend fun setCapability(
        address: String,
        token: String,
        deviceId: String,
        capabilityId: String,
        value: Boolean,
    ): HomeyResult<Unit> = setCapability(address, token, deviceId, capabilityId, JsonPrimitive(value))

    suspend fun setCapability(
        address: String,
        token: String,
        deviceId: String,
        capabilityId: String,
        value: Double,
    ): HomeyResult<Unit> = setCapability(address, token, deviceId, capabilityId, JsonPrimitive(value))

    suspend fun setCapability(
        address: String,
        token: String,
        deviceId: String,
        capabilityId: String,
        value: String,
    ): HomeyResult<Unit> = setCapability(address, token, deviceId, capabilityId, JsonPrimitive(value))

    suspend fun triggerFlow(address: String, token: String, flowId: String): HomeyResult<Unit> =
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url(baseUrl(address) + "/api/manager/flow/flow/$flowId/trigger/")
                .post("{}".toRequestBody(JSON_MEDIA_TYPE))
                .header("Authorization", "Bearer $token")
                .build()
            execute(request) { HomeyResult.Success(Unit) }
        }

    // ───────────────────────────── plumbing ─────────────────────────────

    private suspend fun <T> get(
        address: String,
        token: String,
        path: String,
        transform: (JsonElement) -> T,
    ): HomeyResult<T> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(baseUrl(address) + path)
            .get()
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .build()

        execute(request) { body ->
            val element = json.parseToJsonElement(body)
            HomeyResult.Success(transform(unwrap(element)))
        }
    }

    private inline fun <T> execute(
        request: Request,
        transform: (String) -> HomeyResult<T>,
    ): HomeyResult<T> = try {
        httpClient.newCall(request).execute().use { response ->
            when {
                response.code == 401 || response.code == 403 -> HomeyResult.Failure(
                    reason = "Homey rejected the API key. Create a new Personal Access Token in " +
                        "Homey → Settings → General → API Keys and paste it again.",
                    isAuthError = true,
                )

                response.code == 404 -> HomeyResult.Failure(
                    "Homey answered but does not know that endpoint (${request.url.encodedPath}). " +
                        "This usually means an older firmware version.",
                )

                !response.isSuccessful -> HomeyResult.Failure(
                    "Homey returned HTTP ${response.code} ${response.message}",
                )

                else -> {
                    val body = response.body?.string().orEmpty()
                    if (body.isBlank()) {
                        HomeyResult.Failure("Homey returned an empty response")
                    } else {
                        transform(body)
                    }
                }
            }
        }
    } catch (error: Exception) {
        Log.d(TAG, "Homey request failed: ${request.url}", error)
        HomeyResult.Failure(friendlyError(error))
    }

    private fun friendlyError(error: Exception): String = when (error) {
        is java.net.SocketTimeoutException ->
            "Homey did not respond in time. Check it is powered on and on the same network."

        is java.net.ConnectException ->
            "Could not reach Homey at that address. Check the IP and that you are on home Wi-Fi."

        is java.net.UnknownHostException ->
            "That hostname could not be resolved. Try Homey's IP address instead of a name."

        is javax.net.ssl.SSLException ->
            "TLS handshake failed. Use the plain http:// address for a local Homey."

        else -> error.message ?: "Could not talk to Homey"
    }

    /** Accepts `homey.local`, `192.168.1.10`, or a full URL, and normalises to a base URL. */
    private fun baseUrl(address: String): String {
        val trimmed = address.trim().trimEnd('/')
        return when {
            trimmed.startsWith("http://") || trimmed.startsWith("https://") -> trimmed
            else -> "http://$trimmed"
        }
    }

    /** Unwraps the `{"result": …}` envelope when present. */
    private fun unwrap(element: JsonElement): JsonElement =
        (element as? JsonObject)?.get("result") ?: element

    /**
     * Homey returns collections as an object keyed by id, but some endpoints return arrays.
     * Both are normalised to a list of elements here.
     */
    private fun JsonElement.asObjectValues(): List<JsonElement> = when (this) {
        is JsonObject -> values.toList()
        is JsonArray -> toList()
        else -> emptyList()
    }

    companion object {
        private const val TAG = "HomeyClient"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

        val defaultJson: Json = Json {
            ignoreUnknownKeys = true
            isLenient = true
            coerceInputValues = true
            explicitNulls = false
        }

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(4, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .callTimeout(15, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }
}
