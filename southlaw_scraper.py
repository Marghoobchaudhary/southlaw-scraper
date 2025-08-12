<?php
/**
 * Template Name: Southlaw Scraper Report (DataTable View)
 */
get_header();

function is_price($v) {
    $v = trim((string)$v);
    return ($v !== '' && stripos($v, 'N/A') === false && preg_match('/^\$?\d[\d,]*(\.\d{1,2})?$/', $v));
}
function format_price($v) {
    $num = preg_replace('/[^\d\.]/', '', (string)$v);
    return ($num === '') ? 'N/A' : '$' . number_format((float)$num, 2);
}
function is_integer_like($v) {
    return preg_match('/^\d+$/', trim((string)$v));
}
function normalize_date($v) {
    $v = trim((string)$v);
    if ($v === '' || stripos($v, 'N/A') !== false) return 'N/A';
    $formats = ['n/j/Y','n/j/y','m/d/Y','m/d/y','Y-m-d'];
    foreach ($formats as $fmt) {
        $d = DateTime::createFromFormat($fmt, $v);
        if ($d && $d->format($fmt) === $v) return $d->format('n/j/Y');
    }
    try {
        return (new DateTime($v))->format('n/j/Y');
    } catch (Exception $e) {
        return 'N/A';
    }
}
function extract_dates($item) {
    $dates = [];
    foreach ($item as $val) {
        if (preg_match_all('/\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/', $val, $matches)) {
            foreach ($matches[0] as $date_str) {
                $d = normalize_date($date_str);
                if ($d !== 'N/A') $dates[] = DateTime::createFromFormat('n/j/Y', $d);
            }
        }
    }
    if (!$dates) return ['sale_date' => 'N/A', 'continued_date' => 'N/A'];
    usort($dates, fn($a, $b) => $a <=> $b);
    return [
        'sale_date' => $dates[0]->format('n/j/Y'),
        'continued_date' => (count($dates) > 1) ? end($dates)->format('n/j/Y') : 'N/A'
    ];
}
function extract_zip($item) {
    foreach ($item as $val) {
        if (preg_match_all('/\b(\d{5})(?:-\d{4})?\b/', $val, $matches)) {
            foreach ($matches[1] as $zip) {
                $z = intval($zip);
                if ($z >= 63000 && $z <= 65999) return $zip;
            }
        }
    }
    return 'N/A';
}
?>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>

<div class="sales-report">
    <h1>Sales Report</h1>
    <table id="salesTable" class="display" style="width:100%">
        <thead>
            <tr>
                <th>Address</th>
                <th>ZIP</th>
                <th>Sale Date</th>
                <th>Continued Date</th>
                <th>Opening Bid</th>
                <th>Firm File#</th>
            </tr>
        </thead>
        <tbody>
<?php
$json_url = 'https://raw.githubusercontent.com/Marghoobchaudhary/southlaw-scraper/main/sales_report.json';
$json = @file_get_contents($json_url);

if ($json) {
    $data = json_decode($json, true);
    if (is_array($data) && $data) {
        foreach ($data as $item) {
            // Skip unwanted rows
            if (array_filter($item, fn($v) => stripos($v, 'Information Reported as of') !== false)) continue;

            // Extract dates
            $dates_info = extract_dates($item);
            if ($dates_info['sale_date'] === 'N/A') continue;

            $property_address = $item['property_address'] ?? 'N/A';
            $property_zip = extract_zip($item);
            $opening_bid = is_price($item['opening_bid'] ?? '') ? format_price($item['opening_bid']) : 'N/A';
            $firm_file = is_integer_like($item['firm_file'] ?? '') ? $item['firm_file'] : 'N/A';

            echo '<tr>';
            echo '<td>' . esc_html($property_address) . '</td>';
            echo '<td>' . esc_html($property_zip) . '</td>';
            echo '<td>' . esc_html($dates_info['sale_date']) . '</td>';
            echo '<td>' . esc_html($dates_info['continued_date']) . '</td>';
            echo '<td>' . esc_html($opening_bid) . '</td>';
            echo '<td>' . esc_html($firm_file) . '</td>';
            echo '</tr>';
        }
    }
}
?>
        </tbody>
    </table>
</div>

<script>
jQuery(document).ready(function($) {
    $('#salesTable').DataTable({
        pageLength: 25,
        order: [[2, 'asc']] // Sort by Sale Date
    });
});
</script>

<?php get_footer(); ?>
