package com.hyperscale.command.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hyperscale.command.ui.theme.LocalStatusColours
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/**
 * The scanning visual: concentric range rings, a rotating sweep, and a blip for each device found
 * placed by signal strength.
 *
 * It is genuinely informative rather than decorative — ring distance encodes RSSI (or "IP only,
 * no radio distance" for wired devices, which sit on the outer ring), so the picture answers
 * "what is near me right now" while the scan is still running.
 */
@Composable
fun RadarSweep(
    isScanning: Boolean,
    blips: List<RadarBlip>,
    modifier: Modifier = Modifier,
) {
    val statusColours = LocalStatusColours.current
    val transition = rememberInfiniteTransition(label = "radar")

    val sweepAngle by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2600, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "sweepAngle",
    )

    val pulse by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 2200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "pulse",
    )

    val idleAlpha by animateFloatAsState(
        targetValue = if (isScanning) 1f else 0.35f,
        animationSpec = tween(500),
        label = "idleAlpha",
    )

    val ringColour = MaterialTheme.colorScheme.outlineVariant
    val radarColour = statusColours.radar

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f),
        ) {
            val centre = Offset(size.width / 2f, size.height / 2f)
            val maxRadius = min(size.width, size.height) / 2f * 0.92f

            // Range rings.
            listOf(0.28f, 0.52f, 0.76f, 1f).forEach { fraction ->
                drawCircle(
                    color = ringColour.copy(alpha = 0.5f * idleAlpha),
                    radius = maxRadius * fraction,
                    center = centre,
                    style = Stroke(width = 1.dp.toPx()),
                )
            }

            // Cross hairs.
            drawLine(
                color = ringColour.copy(alpha = 0.3f * idleAlpha),
                start = Offset(centre.x - maxRadius, centre.y),
                end = Offset(centre.x + maxRadius, centre.y),
                strokeWidth = 1.dp.toPx(),
            )
            drawLine(
                color = ringColour.copy(alpha = 0.3f * idleAlpha),
                start = Offset(centre.x, centre.y - maxRadius),
                end = Offset(centre.x, centre.y + maxRadius),
                strokeWidth = 1.dp.toPx(),
            )

            if (isScanning) {
                // Expanding pulse ring, tied to the scan being genuinely active.
                drawCircle(
                    color = radarColour.copy(alpha = (1f - pulse) * 0.35f),
                    radius = maxRadius * pulse,
                    center = centre,
                    style = Stroke(width = 2.dp.toPx()),
                )

                // Rotating sweep wedge.
                val sweepBrush = Brush.sweepGradient(
                    colorStops = arrayOf(
                        0f to Color.Transparent,
                        0.78f to Color.Transparent,
                        0.94f to radarColour.copy(alpha = 0.16f),
                        1f to radarColour.copy(alpha = 0.45f),
                    ),
                    center = centre,
                )
                rotate(degrees = sweepAngle, pivot = centre) {
                    drawCircle(brush = sweepBrush, radius = maxRadius, center = centre)
                }

                // Leading edge of the sweep.
                val radians = Math.toRadians(sweepAngle.toDouble() - 90.0)
                drawLine(
                    color = radarColour,
                    start = centre,
                    end = Offset(
                        x = centre.x + (maxRadius * cos(radians)).toFloat(),
                        y = centre.y + (maxRadius * sin(radians)).toFloat(),
                    ),
                    strokeWidth = 1.5.dp.toPx(),
                )
            }

            // Device blips.
            blips.forEach { blip ->
                val radians = Math.toRadians(blip.angleDegrees.toDouble() - 90.0)
                val distance = maxRadius * blip.normalisedDistance.coerceIn(0.15f, 1f)
                val position = Offset(
                    x = centre.x + (distance * cos(radians)).toFloat(),
                    y = centre.y + (distance * sin(radians)).toFloat(),
                )

                drawCircle(
                    color = blip.colour.copy(alpha = 0.22f),
                    radius = 9.dp.toPx(),
                    center = position,
                )
                drawCircle(
                    color = blip.colour,
                    radius = 3.5.dp.toPx(),
                    center = position,
                )
            }

            // Centre marker: this phone.
            drawCircle(
                color = radarColour,
                radius = 4.dp.toPx(),
                center = centre,
            )
            drawCircle(
                color = radarColour.copy(alpha = 0.25f),
                radius = 11.dp.toPx(),
                center = centre,
            )
        }

        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = blips.size.toString(),
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = if (isScanning) "scanning…" else "devices",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * One point on the radar.
 *
 * [normalisedDistance] runs 0 (right on top of the phone) to 1 (far away or radio-less). Devices
 * with no RSSI are pushed to the outer ring rather than invented a position, which keeps the
 * picture honest.
 */
data class RadarBlip(
    val id: String,
    val angleDegrees: Float,
    val normalisedDistance: Float,
    val colour: Color,
)

/**
 * Distributes devices around the dial deterministically, so a device does not jump position
 * between frames. The angle is derived from a hash of the device id.
 */
fun radarAngleFor(deviceId: String): Float {
    val hash = deviceId.fold(7) { acc, char -> (acc * 31 + char.code) and 0x7FFFFFFF }
    return (hash % 360).toFloat()
}

/** Converts RSSI to a ring position. Devices with no radio reading sit on the outer ring. */
fun radarDistanceFor(rssi: Int?): Float = when {
    rssi == null -> 0.95f
    rssi >= -45 -> 0.2f
    rssi >= -60 -> 0.38f
    rssi >= -72 -> 0.56f
    rssi >= -85 -> 0.74f
    else -> 0.9f
}
