package com.hyperscale.command.ui.adaptive

import android.app.Activity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import androidx.window.layout.FoldingFeature
import androidx.window.layout.WindowInfoTracker
import kotlinx.coroutines.flow.map

/**
 * Physical posture of a foldable, derived from the hinge's own reported state.
 *
 * On a Galaxy Z Fold this is what separates "one big tablet screen" from "a laptop-shaped device
 * standing on a table", which are genuinely different layouts rather than different sizes.
 */
enum class Posture {
    /** No fold, or fully flat: treat the display as one continuous surface. */
    FLAT,

    /** Half-opened with a vertical hinge — held like a book. Content avoids the crease. */
    BOOK,

    /** Half-opened with a horizontal hinge — stood on a surface. Top shows, bottom controls. */
    TABLETOP,
}

data class FoldState(
    val posture: Posture = Posture.FLAT,
    /** True when the hinge physically separates the display into two logical areas. */
    val isSeparating: Boolean = false,
    /** Hinge bounds in window pixel coordinates, or null when there is no hinge to avoid. */
    val hingeLeftPx: Int? = null,
    val hingeRightPx: Int? = null,
    val hingeTopPx: Int? = null,
    val hingeBottomPx: Int? = null,
    /** True on any device that reports a folding feature at all, even when flat. */
    val isFoldable: Boolean = false,
) {
    val hingeWidthPx: Int get() = ((hingeRightPx ?: 0) - (hingeLeftPx ?: 0)).coerceAtLeast(0)
    val hingeHeightPx: Int get() = ((hingeBottomPx ?: 0) - (hingeTopPx ?: 0)).coerceAtLeast(0)

    val isBookMode: Boolean get() = posture == Posture.BOOK && isSeparating
    val isTabletopMode: Boolean get() = posture == Posture.TABLETOP && isSeparating
}

/**
 * Observes the window layout for folding features.
 *
 * Collection is tied to STARTED so a folded-away app is not paying for hinge callbacks, which is
 * exactly the situation the Fold puts an app into every time the user closes it.
 */
@Composable
fun rememberFoldState(): State<FoldState> {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val activity = remember(context) { context.findActivity() }

    if (activity == null) return remember { mutableStateOf(FoldState()) }

    return produceState(initialValue = FoldState(), activity, lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            WindowInfoTracker.getOrCreate(activity)
                .windowLayoutInfo(activity)
                .map { layoutInfo ->
                    val fold = layoutInfo.displayFeatures
                        .filterIsInstance<FoldingFeature>()
                        .firstOrNull()
                        ?: return@map FoldState()

                    val separating = fold.isSeparating
                    val posture = when {
                        fold.state == FoldingFeature.State.FLAT -> Posture.FLAT
                        fold.orientation == FoldingFeature.Orientation.VERTICAL -> Posture.BOOK
                        else -> Posture.TABLETOP
                    }

                    FoldState(
                        posture = posture,
                        isSeparating = separating,
                        hingeLeftPx = fold.bounds.left,
                        hingeRightPx = fold.bounds.right,
                        hingeTopPx = fold.bounds.top,
                        hingeBottomPx = fold.bounds.bottom,
                        isFoldable = true,
                    )
                }
                .collect { value = it }
        }
    }
}

private tailrec fun android.content.Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is android.content.ContextWrapper -> baseContext.findActivity()
    else -> null
}
