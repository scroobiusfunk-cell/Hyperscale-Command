package com.hyperscale.command

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.hyperscale.command.ui.HyperscaleApp
import com.hyperscale.command.ui.HyperscaleViewModel
import com.hyperscale.command.ui.WindowWidth
import com.hyperscale.command.ui.adaptive.rememberFoldState
import com.hyperscale.command.ui.theme.HyperscaleTheme

class MainActivity : ComponentActivity() {

    private lateinit var viewModel: HyperscaleViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val container = (application as HyperscaleApplication).container
        viewModel = ViewModelProvider(
            this,
            HyperscaleViewModel.Factory(container),
        )[HyperscaleViewModel::class.java]

        setContent {
            val settings by container.settingsRepository.settings
                .collectAsStateWithLifecycle(initialValue = com.hyperscale.command.data.AppSettings())

            HyperscaleTheme(useDynamicColour = settings.useDynamicColour) {
                val foldState by rememberFoldState()

                // Width class is derived from the current configuration rather than cached, so a
                // fold, unfold, rotation or split-screen resize re-evaluates it immediately.
                val configuration = LocalConfiguration.current
                val widthClass = when {
                    configuration.screenWidthDp < 600 -> WindowWidth.COMPACT
                    configuration.screenWidthDp < 900 -> WindowWidth.MEDIUM
                    else -> WindowWidth.EXPANDED
                }

                Surface(modifier = Modifier.fillMaxSize()) {
                    HyperscaleApp(
                        viewModel = viewModel,
                        foldState = foldState,
                        widthClass = widthClass,
                        modifier = Modifier
                            .fillMaxSize()
                            .windowInsetsPadding(WindowInsets.safeDrawing)
                            .consumeWindowInsets(WindowInsets.safeDrawing),
                    )
                }
            }
        }
    }

    override fun onStop() {
        super.onStop()
        // Nothing should be polling a hub while the app is not on screen.
        viewModel.stopHomeyPolling()
    }
}
