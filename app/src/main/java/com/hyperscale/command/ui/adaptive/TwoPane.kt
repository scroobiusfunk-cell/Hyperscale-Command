package com.hyperscale.command.ui.adaptive

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

/**
 * A two-pane layout that is aware of the physical hinge.
 *
 * A plain `Row` with weights would happily place a button, or a line of text, directly under the
 * crease of a folded device. This measures where the hinge actually is in window coordinates and
 * splits the panes around it, so nothing lands on the fold. On a flat or non-folding display it
 * degrades to a straightforward weighted split.
 *
 * In tabletop posture the split becomes vertical, matching how the device is physically standing.
 */
@Composable
fun HingeAwareTwoPane(
    foldState: FoldState,
    modifier: Modifier = Modifier,
    firstPaneWeight: Float = 0.38f,
    minPaneWidth: Dp = 280.dp,
    gap: Dp = 20.dp,
    first: @Composable () -> Unit,
    second: @Composable () -> Unit,
) {
    var boundsInWindow by remember { mutableStateOf(Rect.Zero) }

    Layout(
        modifier = modifier.onGloballyPositioned { coordinates ->
            boundsInWindow = coordinates.boundsInWindow()
        },
        content = {
            Box { first() }
            Box { second() }
        },
    ) { measurables, constraints ->
        if (measurables.size < 2) {
            return@Layout layout(constraints.maxWidth, constraints.maxHeight) {}
        }

        val gapPx = gap.roundToPx()
        val minPanePx = minPaneWidth.roundToPx()
        val totalWidth = constraints.maxWidth
        val boundedHeight = constraints.hasBoundedHeight
        val totalHeight = if (boundedHeight) constraints.maxHeight else 0

        // Tabletop: the device is standing up, so stack rather than split side by side.
        // A vertical split needs a bounded height to divide, so it is skipped without one.
        val splitVertically = foldState.isTabletopMode && boundedHeight

        if (splitVertically) {
            val hingeTop = foldState.hingeTopPx
            val hingeBottom = foldState.hingeBottomPx
            val localHingeTop = hingeTop?.minus(boundsInWindow.top.roundToInt())
            val localHingeBottom = hingeBottom?.minus(boundsInWindow.top.roundToInt())

            val firstHeight: Int
            val secondTop: Int
            if (localHingeTop != null && localHingeBottom != null &&
                localHingeTop > 0 && localHingeBottom < totalHeight
            ) {
                firstHeight = localHingeTop.coerceIn(0, totalHeight)
                secondTop = localHingeBottom.coerceIn(firstHeight, totalHeight)
            } else {
                firstHeight = ((totalHeight - gapPx) / 2).coerceAtLeast(0)
                secondTop = firstHeight + gapPx
            }

            val secondHeight = (totalHeight - secondTop).coerceAtLeast(0)
            val firstPlaceable = measurables[0].measure(
                constraints.copy(minHeight = firstHeight, maxHeight = firstHeight),
            )
            val secondPlaceable = measurables[1].measure(
                constraints.copy(minHeight = secondHeight, maxHeight = secondHeight),
            )

            return@Layout layout(totalWidth, totalHeight) {
                firstPlaceable.placeRelative(0, 0)
                secondPlaceable.placeRelative(0, secondTop)
            }
        }

        // Book posture or a flat wide display: split horizontally.
        val localHingeLeft = foldState.hingeLeftPx?.minus(boundsInWindow.left.roundToInt())
        val localHingeRight = foldState.hingeRightPx?.minus(boundsInWindow.left.roundToInt())

        val useHinge = foldState.isBookMode &&
            localHingeLeft != null && localHingeRight != null &&
            localHingeLeft > minPanePx &&
            (totalWidth - localHingeRight) > minPanePx

        val firstWidth: Int
        val secondLeft: Int
        if (useHinge) {
            firstWidth = localHingeLeft!!.coerceIn(0, totalWidth)
            secondLeft = localHingeRight!!.coerceIn(firstWidth, totalWidth)
        } else {
            val proposed = (totalWidth * firstPaneWeight).roundToInt()
            // Never squeeze either pane below a readable width. When the window cannot fit two
            // minimum-width panes at all, fall back to an even split rather than an invalid range.
            val lowerBound = minPanePx.coerceAtMost(totalWidth / 2)
            val upperBound = (totalWidth - gapPx - minPanePx).coerceAtLeast(lowerBound)
            firstWidth = proposed.coerceIn(lowerBound, upperBound)
            secondLeft = (firstWidth + gapPx).coerceAtMost(totalWidth)
        }

        val secondWidth = (totalWidth - secondLeft).coerceAtLeast(0)

        val firstPlaceable = measurables[0].measure(
            constraints.copy(minWidth = firstWidth, maxWidth = firstWidth),
        )
        val secondPlaceable = measurables[1].measure(
            constraints.copy(minWidth = secondWidth, maxWidth = secondWidth),
        )

        val layoutHeight = if (boundedHeight) {
            totalHeight
        } else {
            maxOf(firstPlaceable.height, secondPlaceable.height)
        }

        layout(totalWidth, layoutHeight) {
            firstPlaceable.placeRelative(0, 0)
            secondPlaceable.placeRelative(secondLeft, 0)
        }
    }
}

/**
 * Vertical stack used when the window is too narrow for two panes, kept here so callers can swap
 * between the two without restructuring their content.
 */
@Composable
fun SinglePane(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Column(modifier = modifier) { content() }
}

/** Surface colour for the strip that sits under the hinge, so the crease reads as intentional. */
@Composable
fun hingeSpacerColour() = MaterialTheme.colorScheme.surfaceContainerLowest
