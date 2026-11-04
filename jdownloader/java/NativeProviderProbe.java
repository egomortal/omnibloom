import java.awt.Font;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import javax.imageio.ImageIO;

/** Tiny real providers gate. No JD classes, display, external network or process spawn. */
public final class NativeProviderProbe {
    private static final List<String> completed = new ArrayList<>();
    private static String step = "start";

    public static void main(String[] args) throws Exception {
        if (args.length > 1) throw new IllegalArgumentException("Zero arguments or one fresh owned report path expected");
        String report = args.length == 1 ? args[0] : System.getProperty("omni.jd.providerReport");
        long start = System.nanoTime();
        Throwable failure = null;
        try {
            step = "headless_configuration";
            if (!Boolean.getBoolean("java.awt.headless")) throw new IllegalStateException("Set headless=true before VM startup");
            completed.add(step);
            step = "management_native";
            MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
            if (heap.getUsed() < 0)
                throw new IllegalStateException("Invalid management values");
            completed.add(step);
            step = "awt_toolkit_init";
            Class.forName("java.awt.Toolkit", true, NativeProviderProbe.class.getClassLoader());
            completed.add(step);
            step = "image_native_raster";
            BufferedImage image = new BufferedImage(2, 2, BufferedImage.TYPE_INT_ARGB);
            image.setRGB(1, 1, 0xff123456);
            if (image.getRGB(1, 1) != 0xff123456) throw new IllegalStateException("Raster mismatch");
            completed.add(step);
            step = "font_native_init";
            Font font = new Font("Dialog", Font.PLAIN, 12);
            if (font.getSize() != 12) throw new IllegalStateException("Font metadata mismatch");
            completed.add(step);
            step = "png_memory_roundtrip";
            ByteArrayOutputStream png = new ByteArrayOutputStream();
            if (!ImageIO.write(image, "png", png)) throw new IllegalStateException("PNG writer missing");
            byte[] bytes = png.toByteArray();
            if (bytes.length < 8 || bytes.length > 16384 || bytes[0] != (byte)137 || bytes[1] != 'P')
                throw new IllegalStateException("PNG data invalid");
            BufferedImage decoded = ImageIO.read(new java.io.ByteArrayInputStream(bytes));
            if (decoded == null || decoded.getRGB(1, 1) != 0xff123456) throw new IllegalStateException("PNG decode mismatch");
            completed.add(step);
        } catch (Throwable error) { failure = error; }
        StringBuilder json = new StringBuilder("{\"schema\":\"omni-jd-native-provider-probe/v1\",\"passed\":");
        json.append(failure == null).append(",\"last_step\":\"").append(step).append("\",\"steps\":[");
        for (int i = 0; i < completed.size(); ++i) {
            if (i > 0) json.append(',');
            json.append('"').append(completed.get(i)).append('"');
        }
        json.append("],\"elapsed_ms\":").append((System.nanoTime()-start)/1_000_000);
        json.append(",\"error_class\":\"").append(failure == null ? "" : failure.getClass().getName()).append("\"}\n");
        if (report != null) Files.writeString(Path.of(report), json, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        System.out.print("OMNI_PROVIDER_PROBE_RESULT " + json);
        if (failure != null) throw new IllegalStateException("Native provider probe failed at " + step, failure);
    }
}
