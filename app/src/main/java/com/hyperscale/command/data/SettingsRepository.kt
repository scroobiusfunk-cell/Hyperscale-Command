package com.hyperscale.command.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.discovery.ScanDepth
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "hyperscale_settings",
)

data class AppSettings(
    val homeyAddress: String? = null,
    val homeyToken: String? = null,
    /** Protocol names the user has switched on. Empty means "everything". */
    val enabledProtocols: Set<Protocol> = Protocol.entries.toSet(),
    val scanDepth: ScanDepth = ScanDepth.STANDARD,
    val scanOnLaunch: Boolean = true,
    val continuousDiscovery: Boolean = false,
    val showOfflineDevices: Boolean = true,
    val useDynamicColour: Boolean = true,
    val hasCompletedOnboarding: Boolean = false,
) {
    val isHomeyConfigured: Boolean
        get() = !homeyAddress.isNullOrBlank() && !homeyToken.isNullOrBlank()
}

/**
 * Persisted preferences.
 *
 * The Homey Personal Access Token lives here too. It is a long-lived credential for local hardware
 * and is excluded from cloud backup in `backup_rules.xml`/`data_extraction_rules.xml`, so it never
 * leaves the device.
 */
class SettingsRepository(private val context: Context) {

    val settings: Flow<AppSettings> = context.settingsDataStore.data
        .catch { error ->
            // A corrupt preferences file should degrade to defaults, not crash the app on launch.
            if (error is IOException) emit(emptyPreferences()) else throw error
        }
        .map { preferences ->
            AppSettings(
                homeyAddress = preferences[KEY_HOMEY_ADDRESS]?.takeIf { it.isNotBlank() },
                homeyToken = preferences[KEY_HOMEY_TOKEN]?.takeIf { it.isNotBlank() },
                enabledProtocols = preferences[KEY_ENABLED_PROTOCOLS]
                    ?.mapNotNull { name -> runCatching { Protocol.valueOf(name) }.getOrNull() }
                    ?.toSet()
                    ?: Protocol.entries.toSet(),
                scanDepth = preferences[KEY_SCAN_DEPTH]
                    ?.let { name -> runCatching { ScanDepth.valueOf(name) }.getOrNull() }
                    ?: ScanDepth.STANDARD,
                scanOnLaunch = preferences[KEY_SCAN_ON_LAUNCH] ?: true,
                continuousDiscovery = preferences[KEY_CONTINUOUS] ?: false,
                showOfflineDevices = preferences[KEY_SHOW_OFFLINE] ?: true,
                useDynamicColour = preferences[KEY_DYNAMIC_COLOUR] ?: true,
                hasCompletedOnboarding = preferences[KEY_ONBOARDED] ?: false,
            )
        }

    suspend fun setHomeyCredentials(address: String?, token: String?) {
        context.settingsDataStore.edit { preferences ->
            if (address.isNullOrBlank()) {
                preferences.remove(KEY_HOMEY_ADDRESS)
            } else {
                preferences[KEY_HOMEY_ADDRESS] = address.trim()
            }
            if (token.isNullOrBlank()) {
                preferences.remove(KEY_HOMEY_TOKEN)
            } else {
                preferences[KEY_HOMEY_TOKEN] = token.trim()
            }
        }
    }

    suspend fun setEnabledProtocols(protocols: Set<Protocol>) {
        context.settingsDataStore.edit { preferences ->
            preferences[KEY_ENABLED_PROTOCOLS] = protocols.map { it.name }.toSet()
        }
    }

    suspend fun toggleProtocol(protocol: Protocol, enabled: Boolean) {
        context.settingsDataStore.edit { preferences ->
            val current = preferences[KEY_ENABLED_PROTOCOLS]
                ?: Protocol.entries.map { it.name }.toSet()
            preferences[KEY_ENABLED_PROTOCOLS] =
                if (enabled) current + protocol.name else current - protocol.name
        }
    }

    suspend fun setScanDepth(depth: ScanDepth) {
        context.settingsDataStore.edit { it[KEY_SCAN_DEPTH] = depth.name }
    }

    suspend fun setScanOnLaunch(enabled: Boolean) {
        context.settingsDataStore.edit { it[KEY_SCAN_ON_LAUNCH] = enabled }
    }

    suspend fun setContinuousDiscovery(enabled: Boolean) {
        context.settingsDataStore.edit { it[KEY_CONTINUOUS] = enabled }
    }

    suspend fun setShowOfflineDevices(enabled: Boolean) {
        context.settingsDataStore.edit { it[KEY_SHOW_OFFLINE] = enabled }
    }

    suspend fun setUseDynamicColour(enabled: Boolean) {
        context.settingsDataStore.edit { it[KEY_DYNAMIC_COLOUR] = enabled }
    }

    suspend fun setOnboardingComplete(complete: Boolean) {
        context.settingsDataStore.edit { it[KEY_ONBOARDED] = complete }
    }

    private companion object {
        val KEY_HOMEY_ADDRESS = stringPreferencesKey("homey_address")
        val KEY_HOMEY_TOKEN = stringPreferencesKey("homey_token")
        val KEY_ENABLED_PROTOCOLS = stringSetPreferencesKey("enabled_protocols")
        val KEY_SCAN_DEPTH = stringPreferencesKey("scan_depth")
        val KEY_SCAN_ON_LAUNCH = booleanPreferencesKey("scan_on_launch")
        val KEY_CONTINUOUS = booleanPreferencesKey("continuous_discovery")
        val KEY_SHOW_OFFLINE = booleanPreferencesKey("show_offline")
        val KEY_DYNAMIC_COLOUR = booleanPreferencesKey("dynamic_colour")
        val KEY_ONBOARDED = booleanPreferencesKey("onboarded")
    }
}
