<template>
  <div class="home">
    <section class="hero" :class="{ 'hero--slim': hasPlots }">
      <!-- The ground: a cadastral fabric carrying no labels at all. It shows
           what this is about without wanting to be read, which is why it fades
           out towards the middle, where the field stands. Decorative, so it is
           hidden from anything that reads the page aloud.
           The parcels are a rectangular lattice turned by the street's own
           gradient: every edge on a street sits on its kerb, the side edges are
           square to it, and the widths come from a handful of values, so a run
           of them reads as one Gemarkung rather than as noise. A block between
           two streets is cut into superblocks along the street first, and a
           superblock has *one* rear boundary at a single depth which the row
           fronting the upper street and the row fronting the lower one share.
           That is what makes the two rows meet: both subdivide the same run
           between the same two kerbs, so a parcel can neither overlap the one
           behind it nor leave a strip of paper between them. The box is 3840
           wide because that is the widest monitor anyone brings; a window
           narrower than that is served by `slice`, which crops the sides. -->
      <div class="hero__art" aria-hidden="true">
        <svg viewBox="0 0 3840 1200" preserveAspectRatio="xMidYMin slice">
          <g opacity=".9">
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-181.4,66.4 -32.3,50.7 -63.6,-247.7 -212.8,-232"></polygon>
            <polygon points="-32.3,50.7 79.1,39 55.1,-189.8 -56.3,-178.1"></polygon>
            <polygon points="79.1,39 182.6,28.1 156.4,-220.5 53,-209.7"></polygon>
            <polygon points="182.6,28.1 349.6,10.5 323.5,-238.1 156.4,-220.5"></polygon>
            <polygon points="349.6,10.5 498.8,-5.2 469,-288.6 319.8,-272.9"></polygon>
            <polygon points="498.8,-5.2 602.3,-16 572.5,-299.5 469,-288.6"></polygon>
            <polygon points="602.3,-16 713.6,-27.7 683.8,-311.2 572.5,-299.5"></polygon>
            <polygon points="713.6,-27.7 844.9,-41.5 815.1,-325 683.8,-311.2"></polygon>
            <polygon points="844.9,-41.5 986.1,-56.4 960,-305 818.8,-290.2"></polygon>
            <polygon points="986.1,-56.4 1081.6,-66.4 1050.2,-364.8 954.8,-354.7"></polygon>
            <polygon points="1081.6,-66.4 1248.7,-84 1217.3,-382.3 1050.2,-364.8"></polygon>
            <polygon points="1248.7,-84 1415.8,-101.6 1391.7,-330.3 1224.6,-312.7"></polygon>
            <polygon points="1415.8,-101.6 1572.9,-118.1 1543.1,-401.5 1386,-385"></polygon>
            <polygon points="1572.9,-118.1 1700.2,-131.5 1676.2,-360.2 1548.9,-346.8"></polygon>
            <polygon points="1700.2,-131.5 1867.3,-149 1835.9,-447.4 1668.8,-429.8"></polygon>
            <polygon points="1867.3,-149 1994.6,-162.4 1963.2,-460.8 1835.9,-447.4"></polygon>
            <polygon points="1994.6,-162.4 2098,-173.3 2068.2,-456.7 1964.8,-445.8"></polygon>
            <polygon points="2098,-173.3 2201.4,-184.2 2175.3,-432.8 2071.9,-421.9"></polygon>
            <polygon points="2201.4,-184.2 2296.9,-194.2 2272.9,-422.9 2177.4,-412.9"></polygon>
            <polygon points="2296.9,-194.2 2454,-210.7 2424.2,-494.2 2267.1,-477.6"></polygon>
            <polygon points="2454,-210.7 2621.1,-228.3 2597.1,-457 2430,-439.5"></polygon>
            <polygon points="2621.1,-228.3 2752.4,-242.1 2722.6,-525.5 2591.3,-511.7"></polygon>
            <polygon points="2752.4,-242.1 2863.8,-253.8 2837.6,-502.4 2726.3,-490.7"></polygon>
            <polygon points="2863.8,-253.8 3020.9,-270.3 2991.1,-553.8 2834,-537.2"></polygon>
            <polygon points="3020.9,-270.3 3162.1,-285.2 3138.1,-513.9 2996.9,-499.1"></polygon>
            <polygon points="3162.1,-285.2 3279.5,-297.5 3249.7,-580.9 3132.3,-568.6"></polygon>
            <polygon points="3279.5,-297.5 3410.8,-311.3 3381,-594.7 3249.7,-580.9"></polygon>
            <polygon points="3410.8,-311.3 3506.2,-321.3 3482.2,-550.1 3386.7,-540"></polygon>
            <polygon points="3506.2,-321.3 3609.7,-332.2 3578.3,-630.6 3474.9,-619.7"></polygon>
            <polygon points="3609.7,-332.2 3705.2,-342.3 3675.4,-625.7 3579.9,-615.7"></polygon>
            <polygon points="3705.2,-342.3 3854.3,-357.9 3828.2,-606.6 3679,-590.9"></polygon>
            <polygon points="3854.3,-357.9 3866.3,-359.2 3834.9,-657.5 3823,-656.3"></polygon>
            </g>
            <polygon points="-181.4,66.4 3866.3,-359.2 3873.4,-291.6 -174.3,134" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-174.3,134 -34.4,119.3 -8.3,367.9 -148.2,382.6"></polygon>
            <polygon points="-34.4,119.3 87.6,106.4 113.7,355.1 -8.3,367.9"></polygon>
            <polygon points="87.6,106.4 245.4,89.8 271.5,338.5 113.7,355.1"></polygon>
            <polygon points="-148.2,382.6 -25.5,369.7 -2.6,587.6 -125.3,600.5"></polygon>
            <polygon points="-25.5,369.7 119,354.5 141.9,572.4 -2.6,587.6"></polygon>
            <polygon points="119,354.5 271.5,338.5 294.4,556.3 141.9,572.4"></polygon>
            <polygon points="245.4,89.8 371.7,76.6 396.2,310.3 269.9,323.5"></polygon>
            <polygon points="371.7,76.6 490,64.1 514.6,297.8 396.2,310.3"></polygon>
            <polygon points="269.9,323.5 392.3,310.7 416.7,543.5 294.4,556.3"></polygon>
            <polygon points="392.3,310.7 514.6,297.8 539.1,530.6 416.7,543.5"></polygon>
            <polygon points="490,64.1 585.5,54.1 610.1,287.8 514.6,297.8"></polygon>
            <polygon points="514.6,297.8 610.1,287.8 634.5,520.6 539.1,530.6"></polygon>
            <polygon points="585.5,54.1 724.1,39.5 750.2,288.1 611.6,302.7"></polygon>
            <polygon points="724.1,39.5 876.6,23.5 902.7,272.1 750.2,288.1"></polygon>
            <polygon points="876.6,23.5 1029,7.4 1055.2,256.1 902.7,272.1"></polygon>
            <polygon points="611.6,302.7 754.2,287.7 777.1,505.6 634.5,520.6"></polygon>
            <polygon points="754.2,287.7 920.6,270.2 943.5,488.1 777.1,505.6"></polygon>
            <polygon points="920.6,270.2 1055.2,256.1 1078.1,473.9 943.5,488.1"></polygon>
            <polygon points="1029,7.4 1146.5,-4.9 1171.1,228.8 1053.6,241.2"></polygon>
            <polygon points="1146.5,-4.9 1287.9,-19.8 1312.4,213.9 1171.1,228.8"></polygon>
            <polygon points="1053.6,241.2 1175.1,228.4 1199.5,461.2 1078.1,473.9"></polygon>
            <polygon points="1175.1,228.4 1312.4,213.9 1336.9,446.7 1199.5,461.2"></polygon>
            <polygon points="1287.9,-19.8 1437,-35.4 1456.3,147.6 1307.1,163.3"></polygon>
            <polygon points="1437,-35.4 1564.3,-48.8 1590.5,199.8 1463.2,213.2"></polygon>
            <polygon points="1463.2,213.2 1590.5,199.8 1613.4,417.7 1486.1,431"></polygon>
            <polygon points="1564.3,-48.8 1713.5,-64.5 1736.5,154.3 1587.3,170"></polygon>
            <polygon points="1587.3,170 1736.5,154.3 1762.6,402 1613.4,417.7"></polygon>
            <polygon points="1713.5,-64.5 1830.9,-76.9 1850.7,112.1 1733.4,124.4"></polygon>
            <polygon points="1733.4,124.4 1850.7,112.1 1879.9,389.6 1762.6,402"></polygon>
            <polygon points="1830.9,-76.9 1998,-94.4 2017.8,94.5 1850.7,112.1"></polygon>
            <polygon points="1850.7,112.1 2017.8,94.5 2047,372.1 1879.9,389.6"></polygon>
            <polygon points="1998,-94.4 2147.1,-110.1 2170.1,108.7 2021,124.4"></polygon>
            <polygon points="2021,124.4 2170.1,108.7 2196.2,356.4 2047,372.1"></polygon>
            <polygon points="2147.1,-110.1 2310.2,-127.3 2336.4,121.4 2173.3,138.5"></polygon>
            <polygon points="2310.2,-127.3 2445.5,-141.5 2471.6,107.2 2336.4,121.4"></polygon>
            <polygon points="2173.3,138.5 2315.5,123.6 2338.4,341.4 2196.2,356.4"></polygon>
            <polygon points="2315.5,123.6 2471.6,107.2 2494.5,325 2338.4,341.4"></polygon>
            <polygon points="2445.5,-141.5 2556.9,-153.2 2576.7,35.8 2465.4,47.5"></polygon>
            <polygon points="2465.4,47.5 2576.7,35.8 2605.9,313.3 2494.5,325"></polygon>
            <polygon points="2556.9,-153.2 2677.5,-165.9 2700.5,52.9 2579.9,65.6"></polygon>
            <polygon points="2677.5,-165.9 2834,-182.3 2857,36.5 2700.5,52.9"></polygon>
            <polygon points="2834,-182.3 2990.5,-198.8 3013.5,20 2857,36.5"></polygon>
            <polygon points="2579.9,65.6 2693.9,53.6 2720,301.3 2605.9,313.3"></polygon>
            <polygon points="2693.9,53.6 2853.7,36.8 2879.7,284.5 2720,301.3"></polygon>
            <polygon points="2853.7,36.8 3013.5,20 3039.5,267.7 2879.7,284.5"></polygon>
            <polygon points="2990.5,-198.8 3117.8,-212.2 3140.8,6.6 3013.5,20"></polygon>
            <polygon points="3013.5,20 3140.8,6.6 3166.8,254.3 3039.5,267.7"></polygon>
            <polygon points="3117.8,-212.2 3219.2,-222.8 3240.7,-18.9 3139.2,-8.3"></polygon>
            <polygon points="3219.2,-222.8 3352.5,-236.8 3373.9,-33 3240.7,-18.9"></polygon>
            <polygon points="3139.2,-8.3 3265.5,-21.6 3293.1,241.1 3166.8,254.3"></polygon>
            <polygon points="3265.5,-21.6 3373.9,-33 3401.5,229.7 3293.1,241.1"></polygon>
            <polygon points="3352.5,-236.8 3503,-252.7 3526,-33.9 3375.5,-18"></polygon>
            <polygon points="3503,-252.7 3645.5,-267.6 3668.5,-48.8 3526,-33.9"></polygon>
            <polygon points="3645.5,-267.6 3758.3,-279.5 3781.3,-60.7 3668.5,-48.8"></polygon>
            <polygon points="3375.5,-18 3532.6,-34.6 3558.7,213.1 3401.5,229.7"></polygon>
            <polygon points="3532.6,-34.6 3679.8,-50 3705.9,197.7 3558.7,213.1"></polygon>
            <polygon points="3679.8,-50 3781.3,-60.7 3807.3,187 3705.9,197.7"></polygon>
            <polygon points="3758.3,-279.5 3873.4,-291.6 3899.5,-43 3784.4,-30.9"></polygon>
            <polygon points="3784.4,-30.9 3899.5,-43 3922.4,174.9 3807.3,187"></polygon>
            </g>
            <polygon points="-125.3,600.5 3922.4,174.9 3929.5,242.5 -118.2,668.1" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-118.2,668.1 13.1,654.3 34.5,858.1 -96.7,871.9"></polygon>
            <polygon points="-96.7,871.9 34.5,858.1 62.2,1120.8 -69.1,1134.6"></polygon>
            <polygon points="13.1,654.3 163.3,638.5 183.1,827.4 33,843.2"></polygon>
            <polygon points="163.3,638.5 267.7,627.5 287.6,816.4 183.1,827.4"></polygon>
            <polygon points="33,843.2 145.4,831.4 174.5,1108.9 62.2,1120.8"></polygon>
            <polygon points="145.4,831.4 287.6,816.4 316.7,1094 174.5,1108.9"></polygon>
            <polygon points="267.7,627.5 414.9,612 434.8,801 287.6,816.4"></polygon>
            <polygon points="414.9,612 584,594.2 603.8,783.2 434.8,801"></polygon>
            <polygon points="287.6,816.4 445.7,799.8 474.9,1077.4 316.7,1094"></polygon>
            <polygon points="445.7,799.8 603.8,783.2 633,1060.7 474.9,1077.4"></polygon>
            <polygon points="584,594.2 699.3,582.1 723.9,815.8 608.5,828"></polygon>
            <polygon points="699.3,582.1 814.7,570 839.3,803.7 723.9,815.8"></polygon>
            <polygon points="814.7,570 949.9,555.8 974.5,789.5 839.3,803.7"></polygon>
            <polygon points="608.5,828 744.4,813.7 768.9,1046.4 633,1060.7"></polygon>
            <polygon points="744.4,813.7 864.5,801 888.9,1033.8 768.9,1046.4"></polygon>
            <polygon points="864.5,801 974.5,789.5 999,1022.3 888.9,1033.8"></polygon>
            <polygon points="949.9,555.8 1077.2,542.4 1098.7,746.3 971.4,759.6"></polygon>
            <polygon points="971.4,759.6 1098.7,746.3 1126.3,1008.9 999,1022.3"></polygon>
            <polygon points="1077.2,542.4 1215.8,527.8 1237.2,731.7 1098.7,746.3"></polygon>
            <polygon points="1215.8,527.8 1370.3,511.6 1391.7,715.4 1237.2,731.7"></polygon>
            <polygon points="1370.3,511.6 1493,498.7 1514.4,702.5 1391.7,715.4"></polygon>
            <polygon points="1098.7,746.3 1225.3,732.9 1252.9,995.6 1126.3,1008.9"></polygon>
            <polygon points="1225.3,732.9 1367.9,718 1395.5,980.6 1252.9,995.6"></polygon>
            <polygon points="1367.9,718 1514.4,702.5 1542,965.2 1395.5,980.6"></polygon>
            <polygon points="1493,498.7 1634.2,483.8 1660.3,732.5 1519.1,747.3"></polygon>
            <polygon points="1519.1,747.3 1660.3,732.5 1683.2,950.3 1542,965.2"></polygon>
            <polygon points="1634.2,483.8 1791.3,467.3 1814.3,686.1 1657.2,702.6"></polygon>
            <polygon points="1791.3,467.3 1932.5,452.5 1955.5,671.3 1814.3,686.1"></polygon>
            <polygon points="1657.2,702.6 1793.4,688.3 1819.5,936 1683.2,950.3"></polygon>
            <polygon points="1793.4,688.3 1955.5,671.3 1981.6,919 1819.5,936"></polygon>
            <polygon points="1932.5,452.5 2037.9,441.4 2064.1,690 1958.7,701.1"></polygon>
            <polygon points="2037.9,441.4 2153.3,429.2 2179.5,677.9 2064.1,690"></polygon>
            <polygon points="1958.7,701.1 2069.1,689.5 2092,907.4 1981.6,919"></polygon>
            <polygon points="2069.1,689.5 2179.5,677.9 2202.4,895.7 2092,907.4"></polygon>
            <polygon points="2153.3,429.2 2272,416.8 2295,635.6 2176.3,648"></polygon>
            <polygon points="2272,416.8 2390.7,404.3 2413.7,623.1 2295,635.6"></polygon>
            <polygon points="2390.7,404.3 2563.1,386.2 2586.1,605 2413.7,623.1"></polygon>
            <polygon points="2176.3,648 2291,636 2317.1,883.7 2202.4,895.7"></polygon>
            <polygon points="2291,636 2451.5,619.1 2477.5,866.8 2317.1,883.7"></polygon>
            <polygon points="2451.5,619.1 2586.1,605 2612.1,852.7 2477.5,866.8"></polygon>
            <polygon points="2563.1,386.2 2694.3,372.4 2717.3,591.2 2586.1,605"></polygon>
            <polygon points="2586.1,605 2717.3,591.2 2743.4,838.9 2612.1,852.7"></polygon>
            <polygon points="2694.3,372.4 2814.7,359.7 2836.1,563.6 2715.8,576.2"></polygon>
            <polygon points="2814.7,359.7 2917.1,348.9 2938.5,552.8 2836.1,563.6"></polygon>
            <polygon points="2715.8,576.2 2819.2,565.4 2846.8,828 2743.4,838.9"></polygon>
            <polygon points="2819.2,565.4 2938.5,552.8 2966.1,815.4 2846.8,828"></polygon>
            <polygon points="2917.1,348.9 3045.1,335.5 3066.5,539.4 2938.5,552.8"></polygon>
            <polygon points="3045.1,335.5 3159.1,323.5 3180.5,527.4 3066.5,539.4"></polygon>
            <polygon points="3159.1,323.5 3273.1,311.5 3294.6,515.4 3180.5,527.4"></polygon>
            <polygon points="2938.5,552.8 3055.2,540.6 3082.8,803.2 2966.1,815.4"></polygon>
            <polygon points="3055.2,540.6 3148,530.8 3175.7,793.4 3082.8,803.2"></polygon>
            <polygon points="3148,530.8 3294.6,515.4 3322.2,778 3175.7,793.4"></polygon>
            <polygon points="3273.1,311.5 3392.5,299 3417.1,532.7 3297.7,545.2"></polygon>
            <polygon points="3392.5,299 3511.8,286.4 3536.4,520.1 3417.1,532.7"></polygon>
            <polygon points="3297.7,545.2 3409.1,533.5 3433.6,766.3 3322.2,778"></polygon>
            <polygon points="3409.1,533.5 3536.4,520.1 3560.9,752.9 3433.6,766.3"></polygon>
            <polygon points="3511.8,286.4 3669,269.9 3695.1,518.5 3538,535"></polygon>
            <polygon points="3538,535 3695.1,518.5 3718,736.4 3560.9,752.9"></polygon>
            <polygon points="3669,269.9 3780.3,258.2 3803.3,477 3692,488.7"></polygon>
            <polygon points="3692,488.7 3803.3,477 3829.4,724.7 3718,736.4"></polygon>
            <polygon points="3780.3,258.2 3929.5,242.5 3954.1,476.2 3804.9,491.9"></polygon>
            <polygon points="3804.9,491.9 3954.1,476.2 3978.6,709 3829.4,724.7"></polygon>
            </g>
            <polygon points="-69.1,1134.6 3978.6,709 3985.7,776.6 -62,1202.2" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-62,1202.2 87.2,1186.5 113.3,1435.1 -35.9,1450.8"></polygon>
            <polygon points="-35.9,1450.8 113.3,1435.1 136.2,1653 -13,1668.7"></polygon>
            <polygon points="87.2,1186.5 219.8,1172.5 245.9,1421.2 113.3,1435.1"></polygon>
            <polygon points="219.8,1172.5 362.3,1157.5 388.4,1406.2 245.9,1421.2"></polygon>
            <polygon points="362.3,1157.5 441.2,1149.2 467.3,1397.9 388.4,1406.2"></polygon>
            <polygon points="113.3,1435.1 204.1,1425.5 227,1643.4 136.2,1653"></polygon>
            <polygon points="204.1,1425.5 322.8,1413.1 345.7,1630.9 227,1643.4"></polygon>
            <polygon points="322.8,1413.1 467.3,1397.9 490.3,1615.7 345.7,1630.9"></polygon>
            <polygon points="441.2,1149.2 536.7,1139.2 556.5,1328.2 461.1,1338.2"></polygon>
            <polygon points="536.7,1139.2 640.1,1128.3 660,1317.3 556.5,1328.2"></polygon>
            <polygon points="461.1,1338.2 585.4,1325.1 614.6,1602.7 490.3,1615.7"></polygon>
            <polygon points="585.4,1325.1 660,1317.3 689.2,1594.8 614.6,1602.7"></polygon>
            <polygon points="640.1,1128.3 807.2,1110.8 831.8,1344.5 664.7,1362"></polygon>
            <polygon points="664.7,1362 831.8,1344.5 856.2,1577.3 689.2,1594.8"></polygon>
            <polygon points="807.2,1110.8 959.7,1094.7 981.1,1298.6 828.6,1314.6"></polygon>
            <polygon points="959.7,1094.7 1102.2,1079.8 1123.7,1283.6 981.1,1298.6"></polygon>
            <polygon points="1102.2,1079.8 1240.8,1065.2 1262.2,1269.1 1123.7,1283.6"></polygon>
            <polygon points="828.6,1314.6 976.5,1299.1 1004.1,1561.7 856.2,1577.3"></polygon>
            <polygon points="976.5,1299.1 1132.3,1282.7 1159.9,1545.3 1004.1,1561.7"></polygon>
            <polygon points="1132.3,1282.7 1262.2,1269.1 1289.8,1531.7 1159.9,1545.3"></polygon>
            <polygon points="1240.8,1065.2 1378,1050.8 1402.6,1284.5 1265.4,1298.9"></polygon>
            <polygon points="1378,1050.8 1469.5,1041.1 1494.1,1274.8 1402.6,1284.5"></polygon>
            <polygon points="1265.4,1298.9 1361.8,1288.8 1386.3,1521.5 1289.8,1531.7"></polygon>
            <polygon points="1361.8,1288.8 1494.1,1274.8 1518.6,1507.6 1386.3,1521.5"></polygon>
            <polygon points="1469.5,1041.1 1611.4,1026.2 1631.3,1215.2 1489.4,1230.1"></polygon>
            <polygon points="1611.4,1026.2 1783.1,1008.2 1803,1197.1 1631.3,1215.2"></polygon>
            <polygon points="1783.1,1008.2 1917.1,994.1 1936.9,1183 1803,1197.1"></polygon>
            <polygon points="1489.4,1230.1 1623.3,1216 1652.5,1493.6 1518.6,1507.6"></polygon>
            <polygon points="1623.3,1216 1787.1,1198.8 1816.3,1476.3 1652.5,1493.6"></polygon>
            <polygon points="1787.1,1198.8 1936.9,1183 1966.1,1460.6 1816.3,1476.3"></polygon>
            <polygon points="1917.1,994.1 2044.4,980.7 2070.5,1229.3 1943.2,1242.7"></polygon>
            <polygon points="2044.4,980.7 2175.6,966.9 2201.8,1215.5 2070.5,1229.3"></polygon>
            <polygon points="1943.2,1242.7 2067.5,1229.6 2090.4,1447.5 1966.1,1460.6"></polygon>
            <polygon points="2067.5,1229.6 2201.8,1215.5 2224.7,1433.4 2090.4,1447.5"></polygon>
            <polygon points="2175.6,966.9 2342.7,949.3 2365.7,1168.1 2198.7,1185.7"></polygon>
            <polygon points="2198.7,1185.7 2365.7,1168.1 2391.8,1415.8 2224.7,1433.4"></polygon>
            <polygon points="2342.7,949.3 2461.4,936.9 2484.4,1155.6 2365.7,1168.1"></polygon>
            <polygon points="2461.4,936.9 2594,922.9 2617,1141.7 2484.4,1155.6"></polygon>
            <polygon points="2594,922.9 2744.5,907.1 2767.5,1125.9 2617,1141.7"></polygon>
            <polygon points="2365.7,1168.1 2522.9,1151.6 2548.9,1399.3 2391.8,1415.8"></polygon>
            <polygon points="2522.9,1151.6 2664.1,1136.8 2690.1,1384.5 2548.9,1399.3"></polygon>
            <polygon points="2664.1,1136.8 2767.5,1125.9 2793.6,1373.6 2690.1,1384.5"></polygon>
            <polygon points="2744.5,907.1 2863.9,894.5 2890,1143.2 2770.7,1155.7"></polygon>
            <polygon points="2863.9,894.5 2967.3,883.7 2993.4,1132.3 2890,1143.2"></polygon>
            <polygon points="2967.3,883.7 3100.6,869.7 3126.7,1118.3 2993.4,1132.3"></polygon>
            <polygon points="2770.7,1155.7 2907.9,1141.3 2930.8,1359.2 2793.6,1373.6"></polygon>
            <polygon points="2907.9,1141.3 3025.2,1129 3048.2,1346.8 2930.8,1359.2"></polygon>
            <polygon points="3025.2,1129 3126.7,1118.3 3149.6,1336.2 3048.2,1346.8"></polygon>
            <polygon points="3100.6,869.7 3230.8,856 3255.4,1089.7 3125.1,1103.4"></polygon>
            <polygon points="3230.8,856 3337.2,844.8 3361.8,1078.5 3255.4,1089.7"></polygon>
            <polygon points="3125.1,1103.4 3223.6,1093 3248.1,1325.8 3149.6,1336.2"></polygon>
            <polygon points="3223.6,1093 3361.8,1078.5 3386.3,1311.3 3248.1,1325.8"></polygon>
            <polygon points="3337.2,844.8 3415.8,836.5 3438.8,1055.3 3360.2,1063.6"></polygon>
            <polygon points="3415.8,836.5 3544.1,823 3567.1,1041.8 3438.8,1055.3"></polygon>
            <polygon points="3360.2,1063.6 3451.7,1053.9 3477.8,1301.7 3386.3,1311.3"></polygon>
            <polygon points="3451.7,1053.9 3567.1,1041.8 3593.2,1289.5 3477.8,1301.7"></polygon>
            <polygon points="3544.1,823 3661.5,810.7 3687.6,1059.3 3570.2,1071.7"></polygon>
            <polygon points="3570.2,1071.7 3687.6,1059.3 3710.5,1277.2 3593.2,1289.5"></polygon>
            <polygon points="3661.5,810.7 3773.5,798.9 3794.9,1002.8 3682.9,1014.6"></polygon>
            <polygon points="3773.5,798.9 3863.7,789.4 3885.1,993.3 3794.9,1002.8"></polygon>
            <polygon points="3863.7,789.4 3985.7,776.6 4007.1,980.5 3885.1,993.3"></polygon>
            <polygon points="3682.9,1014.6 3794.3,1002.9 3821.9,1265.5 3710.5,1277.2"></polygon>
            <polygon points="3794.3,1002.9 3931.5,988.4 3959.1,1251 3821.9,1265.5"></polygon>
            <polygon points="3931.5,988.4 4007.1,980.5 4034.7,1243.1 3959.1,1251"></polygon>
            </g>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="var(--w2b-map-surface)"></polygon>
            <path d="M1336.9,446.7 L1486.1,431 L1456.3,147.6 L1307.1,163.3 Z M1360,418.1 L1457.5,407.9 L1433.1,176.2 L1335.7,186.4 Z" fill="var(--w2b-map-setback)" fill-rule="evenodd"></path>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="none" stroke="var(--w2b-map-halo)" stroke-width="7" stroke-linejoin="round"></polygon>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="none" stroke="var(--w2b-map-boundary)" stroke-width="2.4" stroke-linejoin="round"></polygon>
            <polygon points="1360,418.1 1457.5,407.9 1433.1,176.2 1335.7,186.4" fill="none" stroke="var(--w2b-map-envelope)" stroke-width="1.6" stroke-dasharray="8 6"></polygon>
            <polygon points="1369.8,376.9 1443.4,369.2 1432.7,267.7 1359.1,275.4" fill="var(--w2b-map-design)" fill-opacity=".85" stroke="var(--w2b-map-design-edge)" stroke-width="1.8" stroke-linejoin="round"></polygon>

            <!-- A way out, drawn the way `RouteCards` draws a real one: the
                 mode's own colour over the halo every line here carries. It
                 starts on the plot a little below the middle of the building's
                 lower edge -- where a drive leaves a house -- meets the street
                 where the plot fronts it, and follows the centre line east off
                 the page. Starting at the centroid drew the line out through
                 the roof; starting on the wall itself made it read as part of
                 the house rather than as a way away from it.
                 No marker at either end. The far end would claim a destination
                 the start page knows nothing about, and running off the frame
                 survives every viewport where a fixed point does not. The
                 square that marks a start on a route card read as a warning
                 here: it is drawn in the violation colour, and in a backdrop
                 there is no legend behind it to say otherwise. -->
            <g fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1408.6,392 C1409,408 1405.5,424 1406,438 Q1409,468 1440,470 L3980,202.7"
                    stroke="var(--w2b-map-halo)" stroke-width="13" opacity=".85"></path>
              <path d="M1408.6,392 C1409,408 1405.5,424 1406,438 Q1409,468 1440,470 L3980,202.7"
                    stroke="var(--w2b-primary)" stroke-width="4.6"></path>
            </g>
          </g>
        </svg>
      </div>

      <div class="hero__inner">
        <p class="eyebrow hero__eyebrow">{{ greeting }}</p>
        <h1 v-if="hasPlots">Woran heute weiterarbeiten?</h1>
        <h1 v-else>Aus einer Anzeige wird ein <em>geprüftes Grundstück</em>.</h1>

        <p class="hero__sub" v-if="hasPlots">
          Ein neuer Fall beginnt hier. Unten steht, was zuletzt dazukam.
        </p>
        <p class="hero__sub" v-else>
          Link einfügen: gesucht wird das Flurstück im Liegenschaftskataster, gemessen wird
          amtlich, der Preis geht gegen den Bodenrichtwert, und das Haus stellt sich in die
          Abstandsflächen.
        </p>

        <QueryBox class="hero__query panel" :busy="busy" @resolve="startResolve" @read="startRead" />

        <p v-if="signInFailed" class="notice hero__notice" role="alert">
          Die Anmeldung kam nicht zustande. Bitte noch einmal versuchen; ohne Konto lässt sich
          hier ohnehin weiterarbeiten.
        </p>

        <p v-if="!backendUp" class="notice notice--error hero__notice" role="alert">
          Das Backend antwortet nicht. Ohne es lassen sich weder Flurstücke nachschlagen noch
          Seiten auslesen. Gespeicherte Grundstücke bleiben sichtbar.
        </p>

        <div v-if="!hasPlots" class="trust">
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
            <b>Amtliche Flurstücke</b> aus ALKIS
          </span>
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 3v18M8 7h6.5a2.5 2.5 0 0 1 0 5H9a2.5 2.5 0 0 0 0 5h7" />
            </svg>
            <b>Bodenrichtwert</b> zum Stichtag
          </span>
          <span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" />
            </svg>
            <b>Wege nach Fahrplan</b>, nicht Luftlinie
          </span>
        </div>

        <!-- The way into an account, said out loud. The header carries the
             button, but somebody arriving at an empty app looks at the middle
             of the page, not at the top right corner -- and where no provider
             is configured the header shows nothing at all, which read as the
             sign-in being broken rather than absent. Both states say what
             holds. -->
        <p v-if="!state.account.angemeldet" class="hero__account">
          <template v-if="state.account.eingerichtet">
            <a :href="signInHref" @click.prevent="signIn">Anmelden oder Konto anlegen</a> — dann liegt der Stand
            auf jedem Rechner. Ohne Konto bleibt er in diesem Browser, und das reicht
            für alles hier.
          </template>
          <template v-else>
            Ohne Konto: der Stand bleibt in diesem Browser, und das reicht für alles
            hier. Eine Anmeldung ist in diesem Betrieb nicht eingerichtet.
          </template>
        </p>
      </div>
    </section>

    <!-- With a stand: what came in last, and the way to all of it. -->
    <section v-if="hasPlots" class="stack">
      <div class="section-head">
        <h2>Weitermachen</h2>
        <span class="hint">zuletzt hinzugefügt</span>
        <div class="spacer"></div>
        <RouterLink :to="{ name: 'plots' }">{{ allLabel }}</RouterLink>
      </div>
      <div class="card-grid">
        <PlotCard v-for="plot in recent" :key="plot.id" :plot="plot" :selectable="false"
                  @open="open(plot.id)" @remove="remove(plot)" />
      </div>
    </section>

    <!-- Without one: what the thing does, for whoever has not seen it. -->
    <section v-else class="panel">
      <div class="steps">
        <div class="steps__item">
          <p class="eyebrow">Erstens</p>
          <h4>Das Flurstück finden</h4>
          <p>Aus dem, was die Anzeige hergibt: Ortsteil, Fläche, Straße, ein Bild vom
            Katasterauszug. Jeder Schritt steht im Protokoll und lässt sich anfechten.</p>
        </div>
        <div class="steps__item">
          <p class="eyebrow">Zweitens</p>
          <h4>Prüfen, was darauf passt</h4>
          <p>Amtliche Fläche gegen Bodenrichtwert, Abstandsflächen nach § 6 SächsBO,
            Lärm, Hochwasser, Radon. Dazu ein Haustyp im Baufenster.</p>
        </div>
        <div class="steps__item">
          <p class="eyebrow">Drittens</p>
          <h4>Wege messen</h4>
          <p>Zu Arbeit, Schule, Bahnhof, mit dem Fahrplan gerechnet. Die Karte
            druckt sich mit aus.</p>
        </div>
      </div>
      <!-- „Daten“ is a link and not a word, because in the fresh state the
           header carries no sections: naming a place somebody cannot reach
           from here would make this sentence a dead end. -->
      <p class="home__storage">
        {{ storageNote }}
        Zum Mitnehmen gibt es <RouterLink :to="{ name: 'data' }">unter „Daten“</RouterLink>
        den Austausch als JSON.
      </p>
    </section>
  </div>
</template>

<script>
/**
 * The way in.
 *
 * One field for everything, and underneath it either what is already here or
 * what this is for. The page resolves nothing itself: the wizard owns every
 * step after the input, so the input is handed over (`lib/handoff.js`) and the
 * wizard picks it up in its first stage.
 */
import QueryBox from "../components/QueryBox.vue";
import PlotCard from "../components/PlotCard.vue";
import { state, removePlot } from "../lib/store.js";
import { backendHealth, signInUrl } from "../lib/api.js";
import { beginSignIn } from "../lib/signIn.js";
import { handOff } from "../lib/handoff.js";
import { wizardStage } from "../router/stages.js";

/** Enough to pick up where one left off; the list is one click away. */
const RECENT = 3;

export default {
  name: "HomeView",
  components: { QueryBox, PlotCard },
  data() {
    return { state, backendUp: true, busy: false };
  },
  computed: {
    hasPlots() { return state.data.plots.length > 0; },
    /** Named where the provider gave a name, and never claiming a return for
     *  someone who has not been here before. */
    greeting() {
      if (!this.hasPlots) return "Sachsen · Liegenschaftskataster, Bodenrichtwert, Fahrplan";
      const name = state.account.angemeldet ? state.account.name : null;
      return name ? `Willkommen zurück, ${name}` : "Willkommen zurück";
    },
    /** The backend sends the browser back with this when a sign-in broke off.
     *  It carries no detail, and none belongs in a URL. */
    signInFailed() { return this.$route.query.anmeldung === "fehlgeschlagen"; },
    /** Signing in comes back to this page. */
    signInHref() { return signInUrl(this.$route.fullPath); },
    /** Where the stand actually lies. This sentence claimed the server store
     *  was "not built yet" long after it shipped, which is the kind of stale
     *  copy that makes a working feature look missing. It reads the state
     *  instead of asserting one. */
    storageNote() {
      return state.sync.active
        ? "Der Stand liegt in diesem Browser und im Konto, und wird dort gesichert, sobald er sich ändert."
        : "Alles bleibt im Speicher dieses Browsers.";
    },
    plotCount() { return state.data.plots.length; },
    allLabel() {
      return this.plotCount === 1 ? "Zum Grundstück →" : `Alle ${this.plotCount} Grundstücke →`;
    },
    /** Newest first. There is no "changed at" in the document — `readAt` is
     *  when the parcel was read from the cadastre — so the heading says
     *  "hinzugefügt" and not something the data cannot support. */
    recent() {
      return [...state.data.plots]
        .sort((a, b) => String(b.readAt ?? "").localeCompare(String(a.readAt ?? "")))
        .slice(0, RECENT);
    }
  },
  async created() {
    this.backendUp = Boolean(await backendHealth());
  },
  methods: {
    /** Signing in runs in a window of its own, so this page stays standing --
     *  with whatever is half-entered on it. A refused window falls back to a
     *  full navigation; see lib/signIn.js. */
    signIn() { return beginSignIn(this.$route.fullPath); },
    open(id) { this.$router.push({ name: "plot", params: { id } }); },
    remove(plot) {
      const confirmed = window.confirm(`„${plot.name}“ aus der Liste entfernen? Der Stand dieses Grundstücks geht verloren.`);
      if (confirmed) removePlot(plot.id);
    },
    startResolve(payload) {
      handOff({ resolve: payload });
      this.$router.push(wizardStage(0));
    },
    startRead(payload) {
      handOff({ read: payload });
      this.$router.push(wizardStage(0));
    }
  }
};
</script>

<style scoped>
.home{ display: flex; flex-direction: column; gap: var(--w2b-space-6); }

/* The reception. It bleeds to both edges, so it steps out of the container it
   sits in and brings its own. The container stops at 1360 px, and stopping
   with it left the drawing as a panel in the middle of an empty page from
   about 1600 px upwards -- the one place where the page is supposed to be a
   place rather than a card. `100vw` with the auto margin taken back off is
   what reaches the window's own edges; the overshoot of a classic scrollbar
   is clipped by `.shell`, which is why that element carries `overflow-x`. */
.hero{
  position: relative; overflow: hidden;
  display: flex; align-items: center;
  width: 100vw;
  margin: calc(-1 * var(--w2b-space-5)) calc(50% - 50vw) 0;
  padding: var(--w2b-space-8) var(--w2b-space-5);
  border-bottom: 1px solid var(--w2b-line);
  background: var(--w2b-surface);
  /* The reception is the page for somebody arriving, so it gets the screen
     rather than the top of it: the drawing needs room to read as a place, and
     the field needs air around it to look like the one thing to do. Measured
     against the previous fixed padding, this is about a third taller. The
     viewport share is capped so a tall desktop window does not turn it into a
     slide nobody scrolls past. */
  min-height: clamp(600px, 82vh, 940px);
}
/* With a stand, the reception steps aside for the cards below it: the page is
   then about what is already here, not about the invitation. */
.hero--slim{ min-height: 0; padding-top: var(--w2b-space-5); padding-bottom: var(--w2b-space-5); }
.hero--slim h1{ font-size: clamp(26px, 3.2vw, 34px); }
.hero--slim .hero__sub{ font-size: var(--w2b-text-m); }
.hero--slim .hero__query{ margin-top: var(--w2b-space-5); }
/* The cards below carry the picture; here the fabric is only texture. */
.hero--slim .hero__art{ opacity: .34; }

.hero__art{ position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
/* Fixed box, anchored at the top: the suggestion list makes the reception
   taller, and a ground that rescales with it reads as slipped. Tall enough
   that growing never reaches its lower edge, so nothing looks cut off either.
   With `slice` the scale is `max(width/3840, height/1200)`, so up to 4160 px
   of window the height is what sets it: a parcel is the same size on a 1366
   laptop and on a 4K monitor, and a wider window shows more of the fabric
   rather than a magnified piece of it. The plot keeps its distance from the
   middle for the same reason -- the box is centred, so a fixed offset in the
   drawing is a fixed offset on screen. */
.hero__art svg{ display: block; width: 100%; height: max(100%, 1300px); }
/* Towards the middle the fabric gives way to paper: a drawing behind a field
   is a background, and a background must not be read. What has to stay
   readable is the 860 px column of type, and what has to stay legible is the
   plot to the left of it -- both are fixed sizes, so the quiet core is one
   too. Left as a bare 34% it grew with the window until it swallowed the plot;
   470 px is 34% of the width this was drawn at. */
.hero__art::after{
  content: ""; position: absolute; inset: 0;
  background:
    radial-gradient(min(34%, 470px) 42% at 50% 50%,
      var(--w2b-surface) 0 42%,
      color-mix(in srgb, var(--w2b-surface) 84%, transparent) 72%,
      transparent 100%),
    linear-gradient(180deg, transparent 68%, var(--w2b-paper));
}
.hero__inner{
  position: relative; display: flex; flex-direction: column; align-items: center;
  text-align: center; width: 100%; max-width: 860px; margin: 0 auto;
}
.hero__eyebrow{ margin-bottom: var(--w2b-space-3); }
/* Bigger than the page's own h1: this one is the only thing above the field,
   and at the body scale it read as a section heading rather than as a claim. */
.hero h1{ margin-bottom: var(--w2b-space-4); max-width: 20ch; font-size: clamp(34px, 4.8vw, 68px); line-height: 1.06; }
.hero h1 em{ font-style: normal; color: var(--w2b-primary); }
.hero__sub{ color: var(--w2b-graphite); font-size: var(--w2b-text-l); max-width: 56ch; text-wrap: balance; }
.hero__query{ width: 100%; max-width: 760px; margin-top: var(--w2b-space-6); padding: var(--w2b-space-4); text-align: left; }
.hero__notice{ margin-top: var(--w2b-space-4); text-align: left; }
.hero__account{
  margin-top: var(--w2b-space-5); max-width: 62ch;
  font-size: var(--w2b-text-s); color: var(--w2b-muted); text-wrap: balance;
}
.hero__account a{ font-family: var(--w2b-font-display); font-weight: 600; color: var(--w2b-primary); }

.trust{
  display: flex; gap: var(--w2b-space-5); flex-wrap: wrap; justify-content: center;
  margin-top: var(--w2b-space-5); font-size: var(--w2b-text-s); color: var(--w2b-muted);
}
.trust span{ display: inline-flex; align-items: center; gap: 8px; }
.trust svg{ flex: none; color: var(--w2b-primary); }
.trust b{ font-family: var(--w2b-font-display); font-weight: 600; color: var(--w2b-graphite); }

.section-head{ display: flex; align-items: baseline; gap: var(--w2b-space-3); flex-wrap: wrap; }
.section-head h2{ font-size: var(--w2b-text-xl); font-weight: 600; }
.section-head a{ font-family: var(--w2b-font-display); font-weight: 600; font-size: var(--w2b-text-s); text-decoration: none; }
.section-head a:hover{ text-decoration: underline; }

.steps{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--w2b-space-5); padding: var(--w2b-space-5); }
.steps__item h4{ margin-bottom: var(--w2b-space-1); }
.steps__item p{ font-size: var(--w2b-text-s); color: var(--w2b-graphite); }
.steps__item .eyebrow{ margin-bottom: var(--w2b-space-2); }
.home__storage{
  padding: var(--w2b-space-3) var(--w2b-space-5);
  border-top: 1px solid var(--w2b-line-faint);
  font-size: var(--w2b-text-s); color: var(--w2b-muted);
}
.home__storage a{ color: var(--w2b-primary); font-weight: 600; }

@media (max-width: 700px){
  /* At phone widths the fixed box would crop the fabric to a few huge
     parcels; a lower one keeps it readable as what it is. */
  .hero__art svg{ height: max(100%, 820px); }
  /* On a phone the text fills the reception in both directions: the headline
     and the sentence take nearly the whole width, and the field, the three
     lines and the account note take the whole height. A radial core cannot
     rescue that -- widened enough to clear the text it wipes the drawing out,
     and anywhere it fades the fabric runs straight through a line of type,
     which is where a backdrop stops being one.
     So the drawing itself steps back here, and the core only has to soften the
     middle. The opacity goes on the svg and not on `.hero__art`, because the
     veil below is that element's own pseudo-element and would fade with it. */
  .hero__art svg{ opacity: .42; }
  .hero__art::after{
    background:
      radial-gradient(92% 56% at 50% 48%,
        var(--w2b-surface) 0 46%,
        color-mix(in srgb, var(--w2b-surface) 82%, transparent) 78%,
        transparent 100%),
      linear-gradient(180deg, transparent 76%, var(--w2b-paper));
  }
}

@media (max-width: 560px){
  .hero{ padding: var(--w2b-space-7) var(--w2b-space-4); min-height: 0; }
  .hero__sub{ font-size: var(--w2b-text-m); }
}
</style>
