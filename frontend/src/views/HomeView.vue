<template>
  <div class="home">
    <section class="hero" :class="{ 'hero--slim': hasPlots }">
      <!-- The ground: a cadastral fabric carrying no labels at all. It shows
           what this is about without wanting to be read, which is why it fades
           out towards the middle, where the field stands. Decorative, so it is
           hidden from anything that reads the page aloud.
           The parcels are a rectangular lattice turned by the street's own
           gradient: every bottom edge sits on a kerb, the side edges are square
           to it, and the widths and depths come from a handful of values, so a
           run of them reads as one Gemarkung rather than as noise. The box is
           3840 wide because that is the widest monitor anyone brings; a window
           narrower than that is served by `slice`, which crops the sides. -->
      <div class="hero__art" aria-hidden="true">
        <svg viewBox="0 0 3840 1200" preserveAspectRatio="xMidYMin slice">
          <g opacity=".9">
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-290.9,77.9 -123.9,60.3 -155.2,-238 -322.3,-220.5"></polygon>
            <polygon points="-123.9,60.3 43.2,42.7 17.1,-205.9 -150,-188.3"></polygon>
            <polygon points="43.2,42.7 138.7,32.7 114.6,-196 19.2,-186"></polygon>
            <polygon points="138.7,32.7 256,20.4 224.7,-278 107.3,-265.6"></polygon>
            <polygon points="256,20.4 359.5,9.5 329.7,-273.9 226.2,-263.1"></polygon>
            <polygon points="359.5,9.5 486.8,-3.9 462.7,-232.6 335.4,-219.2"></polygon>
            <polygon points="486.8,-3.9 614.1,-17.3 590,-246 462.7,-232.6"></polygon>
            <polygon points="614.1,-17.3 741.4,-30.7 711.6,-314.1 584.3,-300.7"></polygon>
            <polygon points="741.4,-30.7 868.7,-44 838.9,-327.5 711.6,-314.1"></polygon>
            <polygon points="868.7,-44 986,-56.4 962,-285.1 844.6,-272.8"></polygon>
            <polygon points="986,-56.4 1135.2,-72.1 1103.8,-370.4 954.7,-354.7"></polygon>
            <polygon points="1135.2,-72.1 1284.4,-87.7 1253,-386.1 1103.8,-370.4"></polygon>
            <polygon points="1284.4,-87.7 1379.9,-97.8 1348.5,-396.1 1253,-386.1"></polygon>
            <polygon points="1379.9,-97.8 1507.2,-111.2 1481,-359.8 1353.7,-346.4"></polygon>
            <polygon points="1507.2,-111.2 1602.6,-121.2 1571.3,-419.6 1475.8,-409.5"></polygon>
            <polygon points="1602.6,-121.2 1769.7,-138.8 1743.6,-387.4 1576.5,-369.8"></polygon>
            <polygon points="1769.7,-138.8 1936.8,-156.3 1912.7,-385.1 1745.7,-367.5"></polygon>
            <polygon points="1936.8,-156.3 2064.1,-169.7 2040,-398.5 1912.7,-385.1"></polygon>
            <polygon points="2064.1,-169.7 2181.4,-182.1 2157.4,-410.8 2040,-398.5"></polygon>
            <polygon points="2181.4,-182.1 2276.9,-192.1 2245.5,-490.4 2150.1,-480.4"></polygon>
            <polygon points="2276.9,-192.1 2426.1,-207.8 2394.7,-506.1 2245.5,-490.4"></polygon>
            <polygon points="2426.1,-207.8 2521.6,-217.8 2491.8,-501.3 2396.3,-491.2"></polygon>
            <polygon points="2521.6,-217.8 2648.9,-231.2 2624.8,-459.9 2497.5,-446.6"></polygon>
            <polygon points="2648.9,-231.2 2766.2,-243.5 2734.8,-541.9 2617.5,-529.6"></polygon>
            <polygon points="2766.2,-243.5 2915.4,-259.2 2885.6,-542.7 2736.4,-527"></polygon>
            <polygon points="2915.4,-259.2 3018.8,-270.1 2992.7,-518.7 2889.3,-507.8"></polygon>
            <polygon points="3018.8,-270.1 3146.1,-283.5 3116.3,-566.9 2989,-553.5"></polygon>
            <polygon points="3146.1,-283.5 3273.4,-296.9 3249.4,-525.6 3122.1,-512.2"></polygon>
            <polygon points="3273.4,-296.9 3376.8,-307.7 3352.8,-536.5 3249.4,-525.6"></polygon>
            <polygon points="3376.8,-307.7 3543.9,-325.3 3519.9,-554 3352.8,-536.5"></polygon>
            <polygon points="3543.9,-325.3 3671.2,-338.7 3641.4,-622.1 3514.1,-608.7"></polygon>
            <polygon points="3671.2,-338.7 3788.6,-351 3757.2,-649.4 3639.9,-637"></polygon>
            <polygon points="3788.6,-351 3955.7,-368.6 3925.9,-652 3758.8,-634.5"></polygon>
            </g>
            <polygon points="-181.4,66.4 3866.3,-359.2 3873.4,-291.6 -174.3,134" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-311,148.3 -169.7,133.5 -147.8,342.3 -289,357.2"></polygon>
            <polygon points="-169.7,133.5 -38.5,119.7 -18.6,308.6 -149.9,322.4"></polygon>
            <polygon points="-38.5,119.7 102.8,104.8 122.6,293.8 -18.6,308.6"></polygon>
            <polygon points="102.8,104.8 198.2,94.8 224.4,343.4 128.9,353.5"></polygon>
            <polygon points="198.2,94.8 329.5,81 355.7,329.6 224.4,343.4"></polygon>
            <polygon points="329.5,81 486.7,64.5 508.6,273.3 351.5,289.8"></polygon>
            <polygon points="486.7,64.5 643.8,47.9 669.9,296.6 512.8,313.1"></polygon>
            <polygon points="643.8,47.9 755.2,36.2 777.1,245.1 665.7,256.8"></polygon>
            <polygon points="755.2,36.2 912.3,19.7 932.2,208.7 775,225.2"></polygon>
            <polygon points="912.3,19.7 1043.6,5.9 1063.5,194.9 932.2,208.7"></polygon>
            <polygon points="1043.6,5.9 1184.8,-8.9 1204.7,180 1063.5,194.9"></polygon>
            <polygon points="1184.8,-8.9 1296.2,-20.6 1316.1,168.3 1204.7,180"></polygon>
            <polygon points="1296.2,-20.6 1453.3,-37.2 1473.2,151.8 1316.1,168.3"></polygon>
            <polygon points="1453.3,-37.2 1594.5,-52 1616.5,156.8 1475.3,171.7"></polygon>
            <polygon points="1594.5,-52 1751.7,-68.5 1773.6,140.3 1616.5,156.8"></polygon>
            <polygon points="1751.7,-68.5 1847.2,-78.6 1867,110.4 1771.5,120.4"></polygon>
            <polygon points="1847.2,-78.6 1988.4,-93.4 2014.5,155.2 1873.3,170.1"></polygon>
            <polygon points="1988.4,-93.4 2145.5,-109.9 2165.4,79 2008.2,95.5"></polygon>
            <polygon points="2145.5,-109.9 2256.9,-121.6 2278.9,87.2 2167.5,98.9"></polygon>
            <polygon points="2256.9,-121.6 2388.2,-135.4 2408,53.5 2276.8,67.3"></polygon>
            <polygon points="2388.2,-135.4 2519.5,-149.2 2545.6,99.4 2414.3,113.2"></polygon>
            <polygon points="2519.5,-149.2 2650.7,-163 2676.9,85.6 2545.6,99.4"></polygon>
            <polygon points="2650.7,-163 2762.1,-174.8 2782,14.2 2670.6,25.9"></polygon>
            <polygon points="2762.1,-174.8 2919.2,-191.3 2945.4,57.3 2788.3,73.9"></polygon>
            <polygon points="2919.2,-191.3 3060.5,-206.1 3082.4,2.7 2941.2,17.6"></polygon>
            <polygon points="3060.5,-206.1 3217.6,-222.6 3243.7,26 3086.6,42.5"></polygon>
            <polygon points="3217.6,-222.6 3374.7,-239.2 3396.7,-30.3 3239.6,-13.8"></polygon>
            <polygon points="3374.7,-239.2 3470.2,-249.2 3490.1,-60.2 3394.6,-50.2"></polygon>
            <polygon points="3470.2,-249.2 3601.5,-263 3627.6,-14.4 3496.3,-0.6"></polygon>
            <polygon points="3601.5,-263 3697,-273 3718.9,-64.2 3623.4,-54.2"></polygon>
            <polygon points="3697,-273 3828.2,-286.8 3848.1,-97.9 3716.8,-84.1"></polygon>
            <polygon points="3828.2,-286.8 3959.5,-300.6 3985.7,-52 3854.4,-38.2"></polygon>
            </g>
            <polygon points="-125.3,600.5 3922.4,174.9 3929.5,242.5 -118.2,668.1" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-156.9,603.8 -29.6,590.4 -53.7,361.7 -181,375"></polygon>
            <polygon points="-29.6,590.4 87.7,578.1 57.9,294.6 -59.4,307"></polygon>
            <polygon points="87.7,578.1 236.9,562.4 207.1,278.9 57.9,294.6"></polygon>
            <polygon points="236.9,562.4 386.1,546.7 354.7,248.3 205.6,264"></polygon>
            <polygon points="386.1,546.7 481.6,536.7 457.5,307.9 362.1,318"></polygon>
            <polygon points="481.6,536.7 630.8,521 599.4,222.6 450.2,238.3"></polygon>
            <polygon points="630.8,521 797.8,503.4 771.7,254.8 604.6,272.3"></polygon>
            <polygon points="797.8,503.4 893.3,493.4 861.9,195 766.5,205.1"></polygon>
            <polygon points="893.3,493.4 988.8,483.3 959,199.9 863.5,209.9"></polygon>
            <polygon points="988.8,483.3 1116.1,469.9 1084.7,171.6 957.4,185"></polygon>
            <polygon points="1116.1,469.9 1233.4,457.6 1203.6,174.2 1086.3,186.5"></polygon>
            <polygon points="1233.4,457.6 1336.9,446.7 1305.5,148.4 1202.1,159.3"></polygon>
            <polygon points="1486,431.1 1589.5,420.2 1563.3,171.6 1459.9,182.4"></polygon>
            <polygon points="1589.5,420.2 1756.6,402.6 1725.2,104.3 1558.1,121.8"></polygon>
            <polygon points="1756.6,402.6 1852,392.6 1822.2,109.1 1726.8,119.2"></polygon>
            <polygon points="1852,392.6 2019.1,375 1993,126.4 1825.9,143.9"></polygon>
            <polygon points="2019.1,375 2186.2,357.4 2160,108.8 1993,126.4"></polygon>
            <polygon points="2186.2,357.4 2289.6,346.6 2263.5,97.9 2160,108.8"></polygon>
            <polygon points="2289.6,346.6 2416.9,333.2 2387.1,49.7 2259.8,63.1"></polygon>
            <polygon points="2416.9,333.2 2584,315.6 2557.9,67 2390.8,84.6"></polygon>
            <polygon points="2584,315.6 2679.5,305.6 2655.4,76.8 2559.9,86.9"></polygon>
            <polygon points="2679.5,305.6 2774.9,295.5 2745.1,12.1 2649.7,22.1"></polygon>
            <polygon points="2774.9,295.5 2942,278 2912.2,-5.5 2745.1,12.1"></polygon>
            <polygon points="2942,278 3059.4,265.6 3035.3,36.9 2918,49.2"></polygon>
            <polygon points="3059.4,265.6 3176.7,253.3 3152.7,24.6 3035.3,36.9"></polygon>
            <polygon points="3176.7,253.3 3280.2,242.4 3254,-6.2 3150.6,4.7"></polygon>
            <polygon points="3280.2,242.4 3383.6,231.6 3357.4,-17.1 3254,-6.2"></polygon>
            <polygon points="3383.6,231.6 3479.1,221.5 3449.3,-61.9 3353.8,-51.9"></polygon>
            <polygon points="3479.1,221.5 3646.1,204 3620,-44.7 3452.9,-27.1"></polygon>
            <polygon points="3646.1,204 3773.4,190.6 3743.6,-92.9 3616.3,-79.5"></polygon>
            <polygon points="3773.4,190.6 3890.8,178.2 3866.7,-50.5 3749.4,-38.2"></polygon>
            <polygon points="3890.8,178.2 4057.9,160.7 4033.8,-68.1 3866.7,-50.5"></polygon>
            <polygon points="-179.6,674.5 -84.2,664.5 -62.2,873.3 -157.7,883.4"></polygon>
            <polygon points="-84.2,664.5 57.1,649.6 79,858.5 -62.2,873.3"></polygon>
            <polygon points="57.1,649.6 152.5,639.6 174.5,848.4 79,858.5"></polygon>
            <polygon points="152.5,639.6 309.7,623.1 335.8,871.7 178.7,888.2"></polygon>
            <polygon points="309.7,623.1 421.1,611.4 443,820.2 331.6,831.9"></polygon>
            <polygon points="421.1,611.4 552.3,597.6 578.5,846.2 447.2,860"></polygon>
            <polygon points="552.3,597.6 647.8,587.5 669.8,796.4 574.3,806.4"></polygon>
            <polygon points="647.8,587.5 804.9,571 826.9,779.9 669.8,796.4"></polygon>
            <polygon points="804.9,571 916.3,559.3 938.3,768.1 826.9,779.9"></polygon>
            <polygon points="916.3,559.3 1047.6,545.5 1073.7,794.1 942.5,807.9"></polygon>
            <polygon points="1047.6,545.5 1204.7,529 1230.9,777.6 1073.7,794.1"></polygon>
            <polygon points="1204.7,529 1346,514.1 1367.9,723 1226.7,737.8"></polygon>
            <polygon points="1346,514.1 1503.1,497.6 1529.2,746.2 1372.1,762.8"></polygon>
            <polygon points="1503.1,497.6 1598.6,487.6 1618.4,676.5 1523,686.6"></polygon>
            <polygon points="1598.6,487.6 1755.7,471 1777.7,679.9 1620.5,696.4"></polygon>
            <polygon points="1755.7,471 1887,457.2 1906.8,646.2 1775.6,660"></polygon>
            <polygon points="1887,457.2 2018.3,443.4 2044.4,692.1 1913.1,705.9"></polygon>
            <polygon points="2018.3,443.4 2149.5,429.6 2175.7,678.3 2044.4,692.1"></polygon>
            <polygon points="2149.5,429.6 2260.9,417.9 2282.9,626.8 2171.5,638.5"></polygon>
            <polygon points="2260.9,417.9 2392.2,404.1 2412.1,593.1 2280.8,606.9"></polygon>
            <polygon points="2392.2,404.1 2523.5,390.3 2545.4,599.2 2414.2,613"></polygon>
            <polygon points="2523.5,390.3 2618.9,380.3 2640.9,589.1 2545.4,599.2"></polygon>
            <polygon points="2618.9,380.3 2730.3,368.6 2756.5,617.2 2645.1,628.9"></polygon>
            <polygon points="2730.3,368.6 2841.7,356.9 2867.9,605.5 2756.5,617.2"></polygon>
            <polygon points="2841.7,356.9 2973,343.1 2992.9,532 2861.6,545.8"></polygon>
            <polygon points="2973,343.1 3068.5,333 3088.3,522 2992.9,532"></polygon>
            <polygon points="3068.5,333 3209.7,318.2 3235.8,566.8 3094.6,581.7"></polygon>
            <polygon points="3209.7,318.2 3341,304.4 3367.1,553 3235.8,566.8"></polygon>
            <polygon points="3341,304.4 3482.2,289.5 3502.1,478.5 3360.8,493.3"></polygon>
            <polygon points="3482.2,289.5 3639.3,273 3665.5,521.6 3508.3,538.2"></polygon>
            <polygon points="3639.3,273 3750.7,261.3 3772.7,470.2 3661.3,481.9"></polygon>
            <polygon points="3750.7,261.3 3907.8,244.8 3927.7,433.7 3770.6,450.3"></polygon>
            <polygon points="3907.8,244.8 4039.1,231 4061.1,439.8 3929.8,453.6"></polygon>
            </g>
            <polygon points="-69.1,1134.6 3978.6,709 3985.7,776.6 -62,1202.2" fill="var(--w2b-map-street-surface)"></polygon>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-168.9,1145 -1.8,1127.5 -27.9,878.8 -195,896.4"></polygon>
            <polygon points="-1.8,1127.5 115.6,1115.1 85.8,831.7 -31.6,844"></polygon>
            <polygon points="115.6,1115.1 219,1104.3 194.9,875.5 91.5,886.4"></polygon>
            <polygon points="219,1104.3 386.1,1086.7 362,858 194.9,875.5"></polygon>
            <polygon points="386.1,1086.7 553.1,1069.1 521.8,770.8 354.7,788.3"></polygon>
            <polygon points="553.1,1069.1 680.4,1055.8 650.6,772.3 523.3,785.7"></polygon>
            <polygon points="680.4,1055.8 797.8,1043.4 771.7,794.8 654.3,807.1"></polygon>
            <polygon points="797.8,1043.4 947,1027.7 922.9,799 773.7,814.7"></polygon>
            <polygon points="947,1027.7 1050.4,1016.9 1026.4,788.1 922.9,799"></polygon>
            <polygon points="1050.4,1016.9 1199.6,1001.2 1173.4,752.5 1024.3,768.2"></polygon>
            <polygon points="1199.6,1001.2 1295.1,991.1 1268.9,742.5 1173.4,752.5"></polygon>
            <polygon points="1295.1,991.1 1422.4,977.7 1392.6,694.3 1265.3,707.7"></polygon>
            <polygon points="1422.4,977.7 1539.7,965.4 1513.6,716.8 1396.2,729.1"></polygon>
            <polygon points="1539.7,965.4 1643.1,954.5 1617,705.9 1513.6,716.8"></polygon>
            <polygon points="1643.1,954.5 1738.6,944.5 1707.2,646.1 1611.8,656.2"></polygon>
            <polygon points="1738.6,944.5 1865.9,931.1 1836.1,647.7 1708.8,661.1"></polygon>
            <polygon points="1865.9,931.1 1961.4,921.1 1931.6,637.6 1836.1,647.7"></polygon>
            <polygon points="1961.4,921.1 2078.7,908.7 2048.9,625.3 1931.6,637.6"></polygon>
            <polygon points="2078.7,908.7 2174.2,898.7 2142.8,600.3 2047.4,610.4"></polygon>
            <polygon points="2174.2,898.7 2277.6,887.8 2246.3,589.5 2142.8,600.3"></polygon>
            <polygon points="2277.6,887.8 2373.1,877.8 2343.3,594.4 2247.8,604.4"></polygon>
            <polygon points="2373.1,877.8 2476.5,866.9 2452.5,638.2 2349.1,649.1"></polygon>
            <polygon points="2476.5,866.9 2643.6,849.4 2619.6,620.6 2452.5,638.2"></polygon>
            <polygon points="2643.6,849.4 2747.1,838.5 2717.3,555 2613.8,565.9"></polygon>
            <polygon points="2747.1,838.5 2874.4,825.1 2843,526.7 2715.7,540.1"></polygon>
            <polygon points="2874.4,825.1 3041.4,807.5 3015.3,558.9 2848.2,576.5"></polygon>
            <polygon points="3041.4,807.5 3144.9,796.7 3115.1,513.2 3011.6,524.1"></polygon>
            <polygon points="3144.9,796.7 3294,781 3270,552.2 3120.8,567.9"></polygon>
            <polygon points="3294,781 3421.3,767.6 3395.2,519 3267.9,532.3"></polygon>
            <polygon points="3421.3,767.6 3548.6,754.2 3517.3,455.8 3390,469.2"></polygon>
            <polygon points="3548.6,754.2 3675.9,740.8 3651.9,512.1 3524.6,525.5"></polygon>
            <polygon points="3675.9,740.8 3793.3,728.5 3763.5,445 3646.1,457.4"></polygon>
            <polygon points="3793.3,728.5 3896.7,717.6 3866.9,434.2 3763.5,445"></polygon>
            <polygon points="3896.7,717.6 4063.8,700 4037.7,451.4 3870.6,469"></polygon>
            <polygon points="-90.2,1205.1 67,1188.6 86.8,1377.6 -70.3,1394.1"></polygon>
            <polygon points="67,1188.6 178.4,1176.9 198.2,1365.8 86.8,1377.6"></polygon>
            <polygon points="178.4,1176.9 309.6,1163.1 331.6,1371.9 200.3,1385.7"></polygon>
            <polygon points="309.6,1163.1 405.1,1153 425,1342 329.5,1352"></polygon>
            <polygon points="405.1,1153 562.2,1136.5 588.4,1385.2 431.2,1401.7"></polygon>
            <polygon points="562.2,1136.5 673.6,1124.8 693.5,1313.8 582.1,1325.5"></polygon>
            <polygon points="673.6,1124.8 804.9,1111 826.9,1319.9 695.6,1333.7"></polygon>
            <polygon points="804.9,1111 900.4,1101 926.5,1349.6 831,1359.6"></polygon>
            <polygon points="900.4,1101 1057.5,1084.5 1079.5,1293.3 922.3,1309.8"></polygon>
            <polygon points="1057.5,1084.5 1198.7,1069.6 1224.9,1318.2 1083.7,1333.1"></polygon>
            <polygon points="1198.7,1069.6 1355.9,1053.1 1382,1301.7 1224.9,1318.2"></polygon>
            <polygon points="1355.9,1053.1 1487.1,1039.3 1509.1,1248.1 1377.8,1261.9"></polygon>
            <polygon points="1487.1,1039.3 1618.4,1025.5 1640.4,1234.3 1509.1,1248.1"></polygon>
            <polygon points="1618.4,1025.5 1759.6,1010.6 1779.5,1199.6 1638.3,1214.4"></polygon>
            <polygon points="1759.6,1010.6 1855.1,1000.6 1877.1,1209.4 1781.6,1219.5"></polygon>
            <polygon points="1855.1,1000.6 1996.3,985.7 2022.5,1234.4 1881.3,1249.2"></polygon>
            <polygon points="1996.3,985.7 2153.5,969.2 2173.3,1158.2 2016.2,1174.7"></polygon>
            <polygon points="2153.5,969.2 2264.9,957.5 2286.8,1166.4 2175.4,1178.1"></polygon>
            <polygon points="2264.9,957.5 2406.1,942.7 2432.2,1191.3 2291,1206.1"></polygon>
            <polygon points="2406.1,942.7 2547.3,927.8 2569.3,1136.7 2428,1151.5"></polygon>
            <polygon points="2547.3,927.8 2658.7,916.1 2680.6,1125 2569.3,1136.7"></polygon>
            <polygon points="2658.7,916.1 2754.2,906.1 2780.3,1154.7 2684.8,1164.7"></polygon>
            <polygon points="2754.2,906.1 2849.6,896 2869.5,1085 2774,1095"></polygon>
            <polygon points="2849.6,896 2945.1,886 2965,1075 2869.5,1085"></polygon>
            <polygon points="2945.1,886 3040.6,876 3062.5,1084.8 2967.1,1094.8"></polygon>
            <polygon points="3040.6,876 3181.8,861.1 3203.8,1070 3062.5,1084.8"></polygon>
            <polygon points="3181.8,861.1 3293.2,849.4 3315.1,1058.3 3203.8,1070"></polygon>
            <polygon points="3293.2,849.4 3434.4,834.6 3454.3,1023.5 3313.1,1038.4"></polygon>
            <polygon points="3434.4,834.6 3545.8,822.8 3565.7,1011.8 3454.3,1023.5"></polygon>
            <polygon points="3545.8,822.8 3641.3,812.8 3667.4,1061.4 3571.9,1071.5"></polygon>
            <polygon points="3641.3,812.8 3752.7,801.1 3772.5,990.1 3661.1,1001.8"></polygon>
            <polygon points="3752.7,801.1 3909.8,784.6 3931.7,993.4 3774.6,1009.9"></polygon>
            <polygon points="3909.8,784.6 4066.9,768.1 4088.9,976.9 3931.7,993.4"></polygon>
            </g>
            <g fill="var(--w2b-map-ground)" stroke="var(--w2b-map-neighbour)" stroke-width="1.2" stroke-linejoin="round">
            <polygon points="-91.2,1676.9 26.1,1664.5 2.1,1435.8 -115.3,1448.1"></polygon>
            <polygon points="26.1,1664.5 129.6,1653.7 103.4,1405 0,1415.9"></polygon>
            <polygon points="129.6,1653.7 256.9,1640.3 225.5,1341.9 98.2,1355.3"></polygon>
            <polygon points="256.9,1640.3 374.2,1627.9 342.8,1329.6 225.5,1341.9"></polygon>
            <polygon points="374.2,1627.9 477.6,1617.1 451.5,1368.4 348.1,1379.3"></polygon>
            <polygon points="477.6,1617.1 626.8,1601.4 602.8,1372.6 453.6,1388.3"></polygon>
            <polygon points="626.8,1601.4 744.2,1589.1 712.8,1290.7 595.4,1303"></polygon>
            <polygon points="744.2,1589.1 839.6,1579 813.5,1330.4 718,1340.4"></polygon>
            <polygon points="839.6,1579 988.8,1563.3 959,1279.9 809.8,1295.6"></polygon>
            <polygon points="988.8,1563.3 1092.2,1552.5 1068.2,1323.7 964.8,1334.6"></polygon>
            <polygon points="1092.2,1552.5 1219.5,1539.1 1188.2,1240.7 1060.9,1254.1"></polygon>
            <polygon points="1219.5,1539.1 1346.8,1525.7 1317,1242.3 1189.7,1255.6"></polygon>
            <polygon points="1346.8,1525.7 1474.1,1512.3 1442.8,1213.9 1315.5,1227.3"></polygon>
            <polygon points="1474.1,1512.3 1577.6,1501.4 1551.4,1252.8 1448,1263.7"></polygon>
            <polygon points="1577.6,1501.4 1673,1491.4 1649,1262.7 1553.5,1272.7"></polygon>
            <polygon points="1673,1491.4 1790.4,1479.1 1760.6,1195.6 1643.2,1208"></polygon>
            <polygon points="1790.4,1479.1 1939.6,1463.4 1915.5,1234.6 1766.4,1250.3"></polygon>
            <polygon points="1939.6,1463.4 2056.9,1451 2032.9,1222.3 1915.5,1234.6"></polygon>
            <polygon points="2056.9,1451 2184.2,1437.7 2152.9,1139.3 2025.6,1152.7"></polygon>
            <polygon points="2184.2,1437.7 2351.3,1420.1 2319.9,1121.7 2152.9,1139.3"></polygon>
            <polygon points="2351.3,1420.1 2446.8,1410 2422.7,1181.3 2327.3,1191.3"></polygon>
            <polygon points="2446.8,1410 2542.3,1400 2518.2,1171.3 2422.7,1181.3"></polygon>
            <polygon points="2542.3,1400 2691.4,1384.3 2667.4,1155.6 2518.2,1171.3"></polygon>
            <polygon points="2691.4,1384.3 2840.6,1368.6 2810.8,1085.2 2661.6,1100.9"></polygon>
            <polygon points="2840.6,1368.6 3007.7,1351.1 2983.6,1122.3 2816.6,1139.9"></polygon>
            <polygon points="3007.7,1351.1 3174.8,1333.5 3145,1050.1 2977.9,1067.6"></polygon>
            <polygon points="3174.8,1333.5 3323.9,1317.8 3292.6,1019.5 3143.4,1035.2"></polygon>
            <polygon points="3323.9,1317.8 3441.3,1305.5 3417.3,1076.7 3299.9,1089.1"></polygon>
            <polygon points="3441.3,1305.5 3536.8,1295.5 3510.6,1046.8 3415.2,1056.9"></polygon>
            <polygon points="3536.8,1295.5 3632.2,1285.4 3600.9,987.1 3505.4,997.1"></polygon>
            <polygon points="3632.2,1285.4 3735.7,1274.5 3711.6,1045.8 3608.2,1056.7"></polygon>
            <polygon points="3735.7,1274.5 3831.2,1264.5 3805,1015.9 3709.5,1025.9"></polygon>
            <polygon points="3831.2,1264.5 3998.2,1246.9 3972.1,998.3 3805,1015.9"></polygon>
            <polygon points="3998.2,1246.9 4165.3,1229.4 4135.5,945.9 3968.4,963.5"></polygon>
            </g>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="var(--w2b-map-surface)"></polygon>
            <path d="M1336.9,446.7 L1486.1,431 L1456.3,147.6 L1307.1,163.3 Z M1360,418.1 L1457.5,407.9 L1433.1,176.2 L1335.7,186.4 Z" fill="var(--w2b-map-setback)" fill-rule="evenodd"></path>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="none" stroke="var(--w2b-map-halo)" stroke-width="7" stroke-linejoin="round"></polygon>
            <polygon points="1336.9,446.7 1486.1,431 1456.3,147.6 1307.1,163.3" fill="none" stroke="var(--w2b-map-boundary)" stroke-width="2.4" stroke-linejoin="round"></polygon>
            <polygon points="1360,418.1 1457.5,407.9 1433.1,176.2 1335.7,186.4" fill="none" stroke="var(--w2b-map-envelope)" stroke-width="1.6" stroke-dasharray="8 6"></polygon>
            <polygon points="1369.8,376.9 1443.4,369.2 1432.7,267.7 1359.1,275.4" fill="var(--w2b-map-design)" fill-opacity=".85" stroke="var(--w2b-map-design-edge)" stroke-width="1.8" stroke-linejoin="round"></polygon>

            <!-- A way out, drawn the way `RouteCards` draws a real one: the
                 mode's own colour over the halo every line here carries. It
                 starts at the middle of the building's lower edge -- where a
                 drive leaves a house -- meets the street where the plot fronts
                 it, and follows the centre line east off the page. Starting at
                 the centroid instead drew the line out through the roof.
                 No marker at either end. The far end would claim a destination
                 the start page knows nothing about, and running off the frame
                 survives every viewport where a fixed point does not. The
                 square that marks a start on a route card read as a warning
                 here: it is drawn in the violation colour, and in a backdrop
                 there is no legend behind it to say otherwise. -->
            <g fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1406.6,373 C1408,394 1405,418 1406,438 Q1409,468 1440,470 L3980,202.7"
                    stroke="var(--w2b-map-halo)" stroke-width="13" opacity=".85"></path>
              <path d="M1406.6,373 C1408,394 1405,418 1406,438 Q1409,468 1440,470 L3980,202.7"
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
