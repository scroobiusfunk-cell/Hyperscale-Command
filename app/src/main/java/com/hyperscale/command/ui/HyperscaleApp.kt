package com.hyperscale.command.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Hub
import androidx.compose.material.icons.outlined.Radar
import androidx.compose.material.icons.outlined.SettingsEthernet
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.hyperscale.command.ui.adaptive.FoldState
import com.hyperscale.command.ui.screens.devices.DevicesScreen
import com.hyperscale.command.ui.screens.discover.DiscoverScreen
import com.hyperscale.command.ui.screens.homey.HomeyScreen
import com.hyperscale.command.ui.screens.protocols.ProtocolsScreen
import com.hyperscale.command.ui.screens.settings.SettingsScreen

enum class Destination(val label: String, val icon: ImageVector) {
    DISCOVER("Discover", Icons.Outlined.Radar),
    DEVICES("Devices", Icons.Outlined.Dashboard),
    PROTOCOLS("Protocols", Icons.Outlined.SettingsEthernet),
    HOMEY("Homey", Icons.Outlined.Hub),
    SETTINGS("Settings", Icons.Outlined.Tune),
}

/** Window width buckets. Mirrors Material's size classes without depending on their API shape. */
enum class WindowWidth { COMPACT, MEDIUM, EXPANDED }

/**
 * Application shell.
 *
 * The navigation affordance follows available width, not device type: a bottom bar when the window
 * is narrow (cover screen, split-screen, a folded phone) and a side rail when it is wide (the inner
 * display, or a desktop-mode window). The same composables render in both, so unfolding mid-task
 * changes the layout without losing a single piece of state.
 */
@Composable
fun HyperscaleApp(
    viewModel: HyperscaleViewModel,
    foldState: FoldState,
    widthClass: WindowWidth,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val message by viewModel.transientMessage.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    var destination by rememberSaveable { mutableStateOf(Destination.DISCOVER) }

    LaunchedEffect(message) {
        message?.let { text ->
            snackbarHostState.showSnackbar(text)
            viewModel.consumeMessage()
        }
    }

    // Homey is only polled while the app is actually on screen and actually configured.
    LaunchedEffect(uiState.settings.isHomeyConfigured) {
        if (uiState.settings.isHomeyConfigured) {
            viewModel.startHomeyPolling()
        } else {
            viewModel.stopHomeyPolling()
        }
    }

    // On a narrow window the detail pane is a whole screen, so back should close it first.
    BackHandler(enabled = widthClass == WindowWidth.COMPACT && uiState.selectedDeviceId != null) {
        viewModel.selectDevice(null)
    }

    val useRail = widthClass != WindowWidth.COMPACT

    Scaffold(
        modifier = modifier.fillMaxSize(),
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            if (!useRail) {
                NavigationBar {
                    Destination.entries.forEach { entry ->
                        NavigationBarItem(
                            selected = destination == entry,
                            onClick = { destination = entry },
                            icon = { Icon(entry.icon, contentDescription = null) },
                            label = { Text(entry.label) },
                            alwaysShowLabel = false,
                        )
                    }
                }
            }
        },
    ) { padding ->
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (useRail) {
                NavigationRail {
                    Destination.entries.forEach { entry ->
                        NavigationRailItem(
                            selected = destination == entry,
                            onClick = { destination = entry },
                            icon = { Icon(entry.icon, contentDescription = null) },
                            label = { Text(entry.label) },
                        )
                    }
                }
            }

            Box(modifier = Modifier.fillMaxSize()) {
                // A cross-fade rather than a slide: large sliding transitions on a 7.6-inch
                // display read as sluggish, and the rail already shows where you are.
                Crossfade(
                    targetState = destination,
                    animationSpec = tween(durationMillis = 220),
                    label = "destination",
                ) { current ->
                    when (current) {
                        Destination.DISCOVER -> DiscoverScreen(
                            state = uiState,
                            foldState = foldState,
                            widthClass = widthClass,
                            viewModel = viewModel,
                        )

                        Destination.DEVICES -> DevicesScreen(
                            state = uiState,
                            foldState = foldState,
                            widthClass = widthClass,
                            viewModel = viewModel,
                        )

                        Destination.PROTOCOLS -> ProtocolsScreen(
                            state = uiState,
                            viewModel = viewModel,
                            onShowDevices = { destination = Destination.DEVICES },
                        )

                        Destination.HOMEY -> HomeyScreen(
                            state = uiState,
                            widthClass = widthClass,
                            viewModel = viewModel,
                        )

                        Destination.SETTINGS -> SettingsScreen(
                            state = uiState,
                            viewModel = viewModel,
                        )
                    }
                }
            }
        }
    }
}
